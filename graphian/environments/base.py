"""環境・身体が満たす契約 ── 抽象基底(§5.3 / §7.1)。

`Environment` は環境(世界)と身体を 1 つの個体として扱う(集団モデルは初版では不要=決定2)。
クロック A のペースで動き、生死判定を所有し(§3 ③: B に委ねると退化戦略を許すため非対称に
する)、連続適応度を生む(§7.1)。「全個体満腹/全滅」の終了集約は上位(orchestrator)が行う。

接続点の形は身体側が宣言する(§5.3)。本契約ではその経路を `connection_layout`(唯一の宣言源)
として露出し、`reset` 内で `buffer.declare_layout()` へ流す ──「身体 → buffer → B」(§3 ②)を
一本化する。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from graphian.core.buffer import ConnectionBuffer, ConnectionLayout
from graphian.core.genome import BodyGenome


class Environment(ABC):
    """環境-身体(単体個体)の契約。"""

    @property
    @abstractmethod
    def connection_layout(self) -> ConnectionLayout:
        """接続点の形(数・意味・向き)の唯一の宣言源。身体が形を決める(§5.3)。"""

    @abstractmethod
    def reset(
        self,
        body_genome: BodyGenome,
        buffer: ConnectionBuffer,
        rng: np.random.Generator,
    ) -> None:
        """試行を初期化する。

        `buffer.declare_layout(self.connection_layout)` を呼んで形を接続点経路へ流し(§3 ②)、
        身体 genome を反映し、buffer ハンドルを保持する。`buffer` は抽象 interface なので
        in-process でもネットワークでも環境は無改造(transport 非依存の波及 §2.3)。
        """

    @abstractmethod
    def step(self) -> None:
        """クロック A の 1 tick。

        運動(PROC_TO_ENV)を buffer から読み、世界・身体・エネルギーを更新し、生死を判定し、
        感覚(ENV_TO_PROC)を buffer へ書く。頻度は上位が駆動する(§2.2: A:B 比は固定しない)。
        """

    @abstractmethod
    def is_alive(self) -> bool:
        """個体が生存しているか。生死は A が所有する(§3 ③)。False は死(B へ通知され状態破棄)。"""

    @abstractmethod
    def is_done(self) -> bool:
        """この個体の局所終了(満腹 or 死)。終了条件の打ち切り装置の構成要素(§7.1)。"""

    @abstractmethod
    def fitness(self) -> float:
        """連続適応度(§7.1)。生存/死亡の二値ではなく、個体間に淘汰の勾配を与える量。"""
