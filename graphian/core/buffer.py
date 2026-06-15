"""接続点バッファ(§2.3 / §5.3) ── 環境-身体プロセス(クロック A)と情報処理系プロセス
(クロック B)の唯一の接点。

設計の核心は **transport 非依存**(§2.3 末 / §9.8)である:
  - `ConnectionBuffer` を Protocol として定義し、これ自体を「in-process ⇄ ネットワーク」の
    差し替え境界(transport seam)にする。初版は in-process 実装 `InProcessConnectionBuffer`
    を提供し、分散化時には実体だけをネットワーク実装に差し替える。
  - 境界を跨ぐのは **値のスナップショット**(`Snapshot`)と **一度きりの形の宣言**
    (`ConnectionLayout`)だけ。ロック・共有メモリのハンドル・相手側メモリへの参照・
    コールバックは契約に **露出させない**。ゆえに後でソケット送受信へ置換できる。

不変条件(§2.3):
  1. 書き込み時に値を [-1.0, +1.0] にクランプする(初版ダミー方針)。
  2. 最新スナップショットを 1 枚だけ保持する latch。`read` は非ブロッキングで直近の
     確定値を返し、`write` は読み手を待たない ── A:B がどんな頻度比でもロックステップ
     (§2.2 の唯一の禁止事項)にならない。

「形」(接続点の数・意味・向き)は身体側が宣言し、B が読み取る(§5.3)。N 本持てば
「1 環境ノード + 複数情報処理系ノード」を表現でき(§0)、interface は変えずに済む。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, runtime_checkable

import numpy as np

# 接続点の値ベクトル 1 枚。1 次元 float 配列で、**不変として扱う**(writer は retain せず、
# reader は変更しない)。これにより in-process でもネットワークでも「ただのデータ」が渡る。
Snapshot = np.ndarray

# 実装上の dtype。値は概念上 [-1, 1] の実数で、最終的な dtype(§9.2 の暫定 float16)は
# 発達方式とともに §5/§8 で確定する。buffer の契約は dtype に依存しない。
DTYPE = np.float32


class Flow(Enum):
    """接続点の向き。buffer から見た中立な定義(意味づけは環境側が持つ)。"""

    ENV_TO_PROC = auto()  # 感覚: 身体(A)が書き、B が読む
    PROC_TO_ENV = auto()  # 運動: B が書き、身体(A)が読む


@dataclass(frozen=True, slots=True)
class ConnectionPoint:
    """接続点 1 つの宣言。値域は常に [-1, +1] のため range は持たない。"""

    name: str  # 人間/LLM 可読な意味(例 "light_direction", "move")(§9.11)
    flow: Flow


# 接続点の「形」。順序付き・不変。index が transport を跨ぐ安定ハンドルになり、
# 値ベクトル(`Snapshot`)の並びと一致する。
ConnectionLayout = tuple[ConnectionPoint, ...]


@runtime_checkable
class ConnectionBuffer(Protocol):
    """接続点バッファの transport 非依存な契約。

    この Protocol を満たすものは何でも(in-process 実装・将来のネットワーク実装・テスト用
    fake)差し替え可能。`graphian` のどの層もこの型にのみ依存する。
    """

    def declare_layout(self, layout: ConnectionLayout) -> None:
        """接続点の形を宣言する(試行開始時に 1 回だけ §3 ②)。身体側が呼ぶ。"""
        ...

    @property
    def layout(self) -> ConnectionLayout:
        """宣言済みの形。B 側が読み取る経路。宣言前は空。"""
        ...

    def write(self, flow: Flow, values: Snapshot) -> None:
        """`flow` 方向の最新スナップショットを書き込む(値は [-1, 1] にクランプ)。"""
        ...

    def read(self, flow: Flow) -> Snapshot:
        """`flow` 方向の最新確定スナップショットを返す(非ブロッキング)。"""
        ...

    def points(self, flow: Flow) -> tuple[ConnectionPoint, ...]:
        """layout のうち当該 `flow` の接続点(値ベクトルの並びと一致)。"""
        ...

    def close(self) -> None:
        """バッファを閉じる。"""
        ...


class InProcessConnectionBuffer:
    """同一プロセス内の latch 実装(初版)。

    最新スナップショットを 1 枚保持し、スレッド跨ぎの読み書きをロックで保護する
    (§9.8: 初版は最小の並行機構でよい)。分散化時はこのクラスを丸ごとネットワーク
    実装に差し替える ── `ConnectionBuffer` を満たす別物を注入するだけで他層は無改造。
    """

    __slots__ = ("_layout", "_latest", "_lock")

    def __init__(self) -> None:
        self._layout: ConnectionLayout = ()
        self._latest: dict[Flow, np.ndarray] = {}
        self._lock = threading.Lock()

    def declare_layout(self, layout: ConnectionLayout) -> None:
        layout = tuple(layout)
        with self._lock:
            self._layout = layout
            # 形の宣言時点で各方向を中立値(0)で初期化しておく ── read が宣言直後でも
            # 正しい長さのスナップショットを返せる。
            self._latest = {
                Flow.ENV_TO_PROC: np.zeros(self._count(Flow.ENV_TO_PROC), DTYPE),
                Flow.PROC_TO_ENV: np.zeros(self._count(Flow.PROC_TO_ENV), DTYPE),
            }

    @property
    def layout(self) -> ConnectionLayout:
        return self._layout

    def points(self, flow: Flow) -> tuple[ConnectionPoint, ...]:
        return tuple(p for p in self._layout if p.flow is flow)

    def _count(self, flow: Flow) -> int:
        return sum(1 for p in self._layout if p.flow is flow)

    def write(self, flow: Flow, values: Snapshot) -> None:
        # np.array はコピーを作る ── 呼び出し側の配列を共有・破壊しない(latch の独立性)。
        arr = np.array(values, dtype=DTYPE).reshape(-1)
        expected = self._count(flow)
        if arr.shape[0] != expected:
            raise ValueError(
                f"{flow.name} には {expected} 個の値が必要だが {arr.shape[0]} 個渡された"
            )
        np.clip(arr, -1.0, 1.0, out=arr)  # 不変条件 1: 値域を強制(§2.3)。
        with self._lock:
            self._latest[flow] = arr

    def read(self, flow: Flow) -> Snapshot:
        with self._lock:
            current = self._latest.get(flow)
            if current is None:
                return np.zeros(self._count(flow), DTYPE)
            # コピーを返す ── 読み手が触っても内部の latch は不変。
            return current.copy()

    def close(self) -> None:
        # in-process 実装では解放すべき資源はない。
        return None
