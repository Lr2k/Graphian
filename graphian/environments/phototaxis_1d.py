"""1 次元走光性(phototaxis)ダミー環境 / 参照実装(§7.1)。

身体は数直線上の 1 点 x ∈ [-1, 1]。光源は固定位置 x_light(初版は不変)。
エネルギー欠乏で死亡し、満腹(energy = ENERGY_MAX)で試行終了する。
適応度は連続量(光への近さの累積)で、満腹で終わった個体同士でも差がつく(§7.1)。

仕様との対応:
  - 感覚接続点 ×1 : light_direction ─ 右なら正・左なら負を [-1,+1] で返す(§7.1)。
  - 運動接続点 ×1 : move ─ B がここに書いた値 × move_speed で身体が左右に動く(§7.1)。
  - body genome   : move_speed を 1 つ持ち、身体側の進化・継承経路を起動させる(§7.1)。

これは捨てコードではなく「最小の正しい実装例」= 参照実装として残す(§7)。
新しい環境を作る者はまずこれを読んで真似ること(§10)。
"""

from __future__ import annotations

import numpy as np

from graphian.core.buffer import (
    ConnectionBuffer,
    ConnectionLayout,
    ConnectionPoint,
    Flow,
)
from graphian.core.genome import BodyGenome
from graphian.environments.base import Environment

# ---------------------------------------------------------------------------
# エネルギー定数(§7.1)
# ---------------------------------------------------------------------------
_ENERGY_MAX: float = 1.0    # この値に達したら「満腹」= 試行終了(生存)
_ENERGY_INIT: float = 0.5   # 試行開始時のエネルギー
_DRAIN_PER_STEP: float = 0.01    # 毎ステップの消費量(固定)
_RECOVERY_RATE: float = 0.02     # 光の真横(距離 0)での最大回復量。距離に比例して減る。
# 距離 > 0.5 のとき recovery < drain → 遠ければ徐々に死ぬ。
# 距離 0 のとき net gain = 0.01 → 満腹まで約 50 ステップ。


class Phototaxis1DEnvironment(Environment):
    """1 次元走光性の環境 + 身体(§7.1 ダミー / 参照実装)。

    Args:
        x_light: 光源の固定位置。x_light ∈ [-1, 1](§7.1: 初版は不変)。
    """

    def __init__(self, x_light: float = 0.5) -> None:
        if not -1.0 <= x_light <= 1.0:
            raise ValueError(f"x_light は [-1, 1] の範囲でなければならない: {x_light}")
        self._x_light = float(x_light)
        # 以下は reset で上書きされる。型を示すために初期値を置く。
        self._x: float = 0.0
        self._energy: float = _ENERGY_INIT
        self._alive: bool = False
        self._done: bool = False
        self._fitness_accum: float = 0.0
        self._move_speed: float = 0.1
        self._buffer: ConnectionBuffer | None = None

    # ------------------------------------------------------------------
    # 接続点の宣言(§5.3 / §7.1)
    # ------------------------------------------------------------------

    @property
    def connection_layout(self) -> ConnectionLayout:
        """身体が持つ接続点の形(唯一の宣言源 §5.3)。感覚1 + 運動1。"""
        return (
            ConnectionPoint("light_direction", Flow.ENV_TO_PROC),
            ConnectionPoint("move", Flow.PROC_TO_ENV),
        )

    # ------------------------------------------------------------------
    # 試行ライフサイクル(§3 / §7.1)
    # ------------------------------------------------------------------

    def reset(
        self,
        body_genome: BodyGenome,
        buffer: ConnectionBuffer,
        rng: np.random.Generator,
    ) -> None:
        """試行を初期化する。

        接続点の形を buffer へ宣言し(§3 ②)、body genome を反映し、
        初期感覚を書いて B が最初の read で有効な値を得られるようにする。
        """
        self._x = float(rng.uniform(-1.0, 1.0))
        self._energy = _ENERGY_INIT
        self._alive = True
        self._done = False
        self._fitness_accum = 0.0
        self._move_speed = body_genome.move_speed
        self._buffer = buffer
        buffer.declare_layout(self.connection_layout)  # §3 ②: 形を buffer に伝える
        self._write_sensory()  # 初回 B read に備えて初期値を書く

    def step(self) -> None:
        """クロック A の 1 tick(§7.1)。

        運動を読む → 位置・エネルギー更新 → 生死/満腹判定 → 感覚を書く。
        """
        # 運動接続点(PROC_TO_ENV)を読む。初回は 0(中立)。
        motor = float(self._buffer.read(Flow.PROC_TO_ENV)[0])

        # 位置を更新して [-1, 1] に収める(§7.1)。
        self._x = max(-1.0, min(1.0, self._x + motor * self._move_speed))

        # エネルギーを更新(§7.1: 光に近いほど回復)。
        distance = abs(self._x - self._x_light)
        recovery = max(0.0, 1.0 - distance) * _RECOVERY_RATE
        self._energy = max(
            0.0, min(_ENERGY_MAX, self._energy - _DRAIN_PER_STEP + recovery)
        )

        # 連続適応度を累積(§7.1: 光への近さの合計。満腹個体同士でも差がつく)。
        self._fitness_accum += max(0.0, 1.0 - distance)

        # 生死・満腹の判定(§7.1)。判定は環境が所有する(§3 ③)。
        if self._energy <= 0.0:
            self._alive = False
            self._done = True
        elif self._energy >= _ENERGY_MAX:
            # 満腹。_alive のまま。終了条件の打ち切り装置として機能する(§7.1)。
            self._done = True

        # 感覚接続点(ENV_TO_PROC)を書く。buffer がクランプするため計算結果をそのまま渡す。
        self._write_sensory()

    # ------------------------------------------------------------------
    # 状態の問い合わせ(§5.3 / §7.1)
    # ------------------------------------------------------------------

    def is_alive(self) -> bool:
        """生存しているか(§3 ③: 生死は環境が所有)。"""
        return self._alive

    def is_done(self) -> bool:
        """この個体の局所終了(満腹 or 死)。orchestrator が全体終了を集約する(§7.1)。"""
        return self._done

    def fitness(self) -> float:
        """連続適応度 = 光への近さの累積(§7.1)。二値でなく個体間に勾配を与える量。"""
        return self._fitness_accum

    # ------------------------------------------------------------------
    # 内部ヘルパ
    # ------------------------------------------------------------------

    @property
    def position(self) -> float:
        """現在の身体位置(オーケストレータがスナップショットを書くために使う)。"""
        return self._x

    @property
    def energy(self) -> float:
        """現在のエネルギー量(オーケストレータがスナップショットを書くために使う)。"""
        return self._energy

    def _write_sensory(self) -> None:
        """現在位置から光の方向を計算して buffer へ書く。

        x_light - x は右なら正・左なら負。[-2, 2] 範囲になり得るが buffer がクランプする。
        """
        direction = self._x_light - self._x
        self._buffer.write(
            Flow.ENV_TO_PROC, np.array([direction], dtype=np.float32)
        )
