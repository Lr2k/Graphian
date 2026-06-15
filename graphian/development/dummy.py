"""ダミー発達ルール + ダミーネットワーク / 参照実装(§7.2)。

ダミーは賢くある必要はないが、§7.2 が定める 4 つの契約点をすべて一度は通過させなければ
骨格の検証にならない(§7 原則)。以下の 4 点がいずれかのメソッドで必ず起動する:

  1. 接続点ノードの配置(`initialize` → `network.place_connection_nodes`)
  2. ノードとエッジの **追加・削除の両方**(`initialize` → `_exercise_add_remove`)
     + 報酬系ノードの固定配置(`initialize` → `network.add_node(genome.reward_node)`)
  3. 運動接続点への値の書き戻し(`step` → `network.set_value`)
  4. 演算予算の消費と打ち切り(`step` → `budget.charge` / `budget.exhausted`)

これは捨てコードではなく「最小の正しい実装例」= 参照実装として残す(§7)。
具体的な発達の数学は §8 で本クラスに差し替わる。

`DummyNetwork` について:
  情報処理基盤の構造(統合・活性化・伝播)は系統=§8 と一対一対応するため(決定1)、
  `Network` は core では抽象基底に留まる。本ファイルに最小具象実装 `DummyNetwork` を置き、
  `DummyDevelopmentRule` と対で使う参照実装とする。接続点専用円のインデックスは
  `genome.num_circles`(genome の円の外)とする慣例を両クラスで共有する。
"""

from __future__ import annotations

import numpy as np

from graphian.core.buffer import ConnectionLayout, Flow, Snapshot
from graphian.core.genome import NetworkGenome
from graphian.core.geometry import Geometry, NodePosition
from graphian.core.network import Network
from graphian.development.base import Budget, DevelopmentContext, DevelopmentRule


# ---------------------------------------------------------------------------
# FixedBudget: 演算予算の最小具象実装(§9.7)
# ---------------------------------------------------------------------------


class FixedBudget:
    """固定演算予算(§9.7)。

    バジェット N の具体値と超過時の方針(打切り/罰)は §8 で保留。初版ダミーは
    「フレームだけ起動」= 消費して尽きたかを問えること(§7.2-4)を満たす最小実装。
    """

    def __init__(self, n: int = 1000) -> None:
        self._remaining = n

    @property
    def remaining(self) -> int:
        return self._remaining

    def charge(self, ops: int) -> None:
        self._remaining = max(0, self._remaining - ops)

    def exhausted(self) -> bool:
        return self._remaining <= 0


# ---------------------------------------------------------------------------
# DummyNetwork: Network 抽象基底の最小具象実装(§7.2 / 決定1)
# ---------------------------------------------------------------------------


class DummyNetwork(Network):
    """ダミー/参照実装の同心円グラフ。

    `Network` 契約の全メソッドを最小限で実装し、骨格の contract point を通過させる。
    接続点専用円のインデックス = `genome.num_circles`(genome が持つ円の外側)(§5.1末)。
    値の統合・活性化・伝播は系統=§8 で決まるため、本クラスは持たない(決定1)。
    """

    def __init__(self, genome: NetworkGenome) -> None:
        self._geom = Geometry.from_circles(
            genome.slots_per_circle, genome.circle_diameters
        )
        self._reward_pos = genome.reward_node
        # 接続点専用円のインデックス(DummyDevelopmentRule と共有する慣例)。
        self._conn_circle: int = genome.num_circles
        self._conn_layout: ConnectionLayout = ()
        self._nodes: dict[NodePosition, float] = {}
        self._edges: set[frozenset] = set()
        # flow 別の接続点スロット番号(layout の index に対応)。
        self._env_to_proc_slots: list[int] = []
        self._proc_to_env_slots: list[int] = []

    # --- 構造の問い合わせ ---

    @property
    def geometry(self) -> Geometry:
        return self._geom

    def has_node(self, pos: NodePosition) -> bool:
        return pos in self._nodes

    def neighbors(self, pos: NodePosition) -> tuple[NodePosition, ...]:
        result = []
        for edge in self._edges:
            items = list(edge)
            if len(items) == 2:
                a, b = items
                if pos == a:
                    result.append(b)
                elif pos == b:
                    result.append(a)
        return tuple(result)

    # --- 構造の変異 ---

    def add_node(self, pos: NodePosition) -> None:
        if pos in self._nodes:
            return
        if pos.circle == self._conn_circle:
            # 接続点専用円: layout の長さが容量の上限。
            if pos.slot >= len(self._conn_layout):
                raise ValueError(
                    f"接続点スロット {pos.slot} が layout 長 {len(self._conn_layout)} を超える"
                )
        elif not self._geom.contains(pos):
            raise ValueError(
                f"NodePosition {pos} はジオメトリの範囲外(スロット容量超過 §5.1/§9.7)"
            )
        self._nodes[pos] = 0.0

    def remove_node(self, pos: NodePosition) -> None:
        if pos not in self._nodes:
            return
        del self._nodes[pos]
        # 関連エッジを除去(§7.2-2 の削除経路)。
        self._edges = {e for e in self._edges if pos not in e}

    def add_edge(self, a: NodePosition, b: NodePosition) -> None:
        self._edges.add(frozenset({a, b}))

    def remove_edge(self, a: NodePosition, b: NodePosition) -> None:
        self._edges.discard(frozenset({a, b}))

    # --- 値 ---

    def value(self, pos: NodePosition) -> float:
        return self._nodes.get(pos, 0.0)

    def set_value(self, pos: NodePosition, v: float) -> None:
        if pos in self._nodes:
            self._nodes[pos] = float(v)

    # --- 特別ノードと接続点 I/O ---

    @property
    def reward_node(self) -> NodePosition:
        return self._reward_pos

    def place_connection_nodes(self, layout: ConnectionLayout) -> None:
        """接続点ノードを接続点専用円(インデックス = genome.num_circles)へ配置する(§7.2-1)。"""
        self._conn_layout = layout
        self._env_to_proc_slots = []
        self._proc_to_env_slots = []
        for i, pt in enumerate(layout):
            pos = NodePosition(self._conn_circle, i)
            self._nodes[pos] = 0.0
            if pt.flow == Flow.ENV_TO_PROC:
                self._env_to_proc_slots.append(i)
            else:
                self._proc_to_env_slots.append(i)

    def write_inputs(self, sensory: Snapshot) -> None:
        """感覚スナップショットを ENV_TO_PROC 接続点ノードへ流し込む。"""
        for j, slot in enumerate(self._env_to_proc_slots):
            pos = NodePosition(self._conn_circle, slot)
            if pos in self._nodes and j < len(sensory):
                self._nodes[pos] = float(sensory[j])

    def read_outputs(self) -> Snapshot:
        """PROC_TO_ENV 接続点ノードの値をスナップショットとして取り出す。"""
        arr = np.zeros(len(self._proc_to_env_slots), dtype=np.float32)
        for j, slot in enumerate(self._proc_to_env_slots):
            pos = NodePosition(self._conn_circle, slot)
            arr[j] = self._nodes.get(pos, 0.0)
        return arr

    def all_nodes(self) -> tuple[NodePosition, ...]:
        return tuple(self._nodes.keys())

    def all_edges(self) -> tuple[tuple[NodePosition, NodePosition], ...]:
        result = []
        for edge in self._edges:
            items = list(edge)
            if len(items) == 2:
                result.append((items[0], items[1]))
        return tuple(result)


# ---------------------------------------------------------------------------
# 内部ヘルパ
# ---------------------------------------------------------------------------


def _exercise_add_remove(network: Network, genome: NetworkGenome) -> None:
    """§7.2-2: ノードとエッジの追加・削除を両方一度実行する。

    報酬ノードがすでに追加済みであることを前提に、それとは別の一時ノードを使って
    追加→エッジ追加→エッジ削除→ノード削除の 4 経路をすべて通す。

    genome が 1 スロットしか持たない極端なケース(報酬ノード以外の位置が存在しない)では
    この操作をスキップする。ダミーの検証目的では genome に複数スロットを与えること。
    """
    temp: NodePosition | None = None
    for c in range(genome.num_circles):
        for s in range(genome.slots_per_circle[c]):
            p = NodePosition(c, s)
            if p != genome.reward_node:
                temp = p
                break
        if temp is not None:
            break
    if temp is None:
        return  # 全スロット = 1 の極端なゲノム: スキップ。
    network.add_node(temp)
    network.add_edge(genome.reward_node, temp)
    network.remove_edge(genome.reward_node, temp)
    network.remove_node(temp)


# ---------------------------------------------------------------------------
# DummyDevelopmentRule: DevelopmentRule 抽象基底の最小具象実装(§7.2)
# ---------------------------------------------------------------------------


class DummyDevelopmentRule(DevelopmentRule):
    """ダミー発達ルール(§7.2 参照実装)。

    中身は乱数だが §7.2 の 4 つの契約点を必ず通過させる。
    `DummyNetwork` と対になる実装。接続点専用円のインデックス = `genome.num_circles`
    という慣例を `initialize` で直接計算し、`step` でモータノードへ書き戻す。
    """

    def __init__(self) -> None:
        # initialize で設定する。step で使うため保持する。
        self._motor_nodes: tuple[NodePosition, ...] = ()

    def initialize(
        self,
        ctx: DevelopmentContext,
        layout: ConnectionLayout,
        genome: NetworkGenome,
    ) -> None:
        """試行開始時の初期化。§7.2 の契約点 1・2 をここで通す。

        1. 接続点ノードを直径 1 の専用円へ配置(§7.2-1)。
        2. 報酬系ノードを genome 規定位置へ固定配置(§7.2-2)。
        3. ノードとエッジの追加・削除を両方実行(§7.2-2)。
        """
        # 接続点専用円のインデックスは genome.num_circles(DummyNetwork の慣例)。
        conn_circle = genome.num_circles
        # step で set_value を呼ぶ PROC_TO_ENV ノード位置を先に決める。
        self._motor_nodes = tuple(
            NodePosition(conn_circle, i)
            for i, pt in enumerate(layout)
            if pt.flow == Flow.PROC_TO_ENV
        )

        # §7.2-1: 接続点ノードを配置。
        ctx.network.place_connection_nodes(layout)

        # §7.2-2: 報酬系ノードを genome 規定位置へ固定配置(消えない足場 §5.2)。
        ctx.network.add_node(genome.reward_node)

        # §7.2-2: ノードとエッジの追加・削除の両経路を起動。
        _exercise_add_remove(ctx.network, genome)

    def step(self, ctx: DevelopmentContext) -> None:
        """1 B-tick。§7.2 の契約点 3・4 をここで通す。

        4. 演算予算を消費し、尽きたら打ち切る(§7.2-4)。
        3. 運動接続点へ乱数を書き戻す ── 入力→出力の経路が繋がること(§7.2-3)。
        """
        # §7.2-4: 予算を消費して打ち切る。
        ctx.budget.charge(1)
        if ctx.budget.exhausted():
            return

        # §7.2-3: 運動接続点ノードへ乱数を書き戻す(中身は乱数でよい §7.2)。
        for pos in self._motor_nodes:
            ctx.network.set_value(pos, float(ctx.rng.uniform(-1.0, 1.0)))
