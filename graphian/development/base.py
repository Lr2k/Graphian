"""発達ルールが満たす契約 ── **抽象基底のみ。数学は一切書かない**(§1 / §8)。

【契約が §8 未確定でも固まる理由】
  `DevelopmentRule` が露出するのは **ライフサイクルだけ** である:
    - `initialize` : 接続点ノードの配置 + 報酬系ノードを genome 規定位置へ固定配置(§7.2-1,2)。
    - `step`       : 1 B-tick(感覚読取 → ノード/エッジの追加・削除 → 運動書込)を予算内で。
  §8 で決める「報酬に応じた追加/削除確率」「角度分布」「距離カーネル」「活動依存」は、すべて
  この 2 メソッドの **本体の中身** と `NetworkGenome` への **フィールド追加** で入る。シグネチャ
  は不変であり、ダミー(§7.2)も将来の本物も同じ契約に乗る。

  さらに情報処理基盤の構造そのもの(値の統合・活性化・伝播)は系統(§9.5)=§8 と一対一対応する
  (決定1)。よってここにも、`Network` 側にも、その数学は置かない。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from graphian.core.buffer import ConnectionLayout
from graphian.core.genome import NetworkGenome
from graphian.core.network import Network


@runtime_checkable
class Budget(Protocol):
    """演算回数ベースの計算予算(§9.7)。

    時間ではなく演算回数(ノード更新・エッジ評価)で区切ることで、遅いマシンでも速い
    マシンでも公平・決定的になる。バジェット N の具体値と超過時の扱い(打切り/罰)は
    §8 で決めるため、契約は「消費して尽きたか問える」だけに留める。
    """

    @property
    def remaining(self) -> int:
        """残り演算回数。"""
        ...

    def charge(self, ops: int) -> None:
        """演算回数を消費する。"""
        ...

    def exhausted(self) -> bool:
        """予算を使い切ったか。"""
        ...


@dataclass
class DevelopmentContext:
    """1 B-tick の発達に必要な素材を束ねる(数学ではなく入出力の口)。

    感覚値・運動値は `Network` の接続点ノード経由でやり取りするため(§5.1: 接続点も実ノード)、
    ここには含めない ── 発達ルールは buffer を直接触らず `network` だけを見ればよい。
    """

    network: Network
    budget: Budget
    rng: np.random.Generator  # genome.seed 由来。確率挙動を唯一のシード系列に閉じ込める。


class DevelopmentRule(ABC):
    """発達ルールの契約。具象(ダミー §7.2 / 本物 §8)はこの 2 メソッドの中身を差し替える。"""

    @abstractmethod
    def initialize(
        self,
        ctx: DevelopmentContext,
        layout: ConnectionLayout,
        genome: NetworkGenome,
    ) -> None:
        """試行開始時の初期化(§7.2-1,2)。

        宣言された形(`layout`)を受けて接続点ノードを配置し、報酬系ノードを genome 規定の
        位置へ固定配置する。
        """

    @abstractmethod
    def step(self, ctx: DevelopmentContext) -> None:
        """1 B-tick の発達(§7.2-2,3,4)。

        接続点ノードの感覚値を読み、ノード/エッジを追加・削除し、運動接続点へ値を書き戻す。
        `ctx.budget` を消費し、尽きたら打ち切る。
        """
