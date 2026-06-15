"""情報処理系ネットワークの実行時状態(同心円グラフ)の契約 ── **抽象基底のみ**。

`Network` は「いま実際にどのノードが存在し、どんなエッジがあり、各ノードがどんな値を持つか」
という生きた状態を保持する箱であり、`Geometry`(状態を持たない定規)の上に建つ「街」に当たる。

【なぜ core では抽象基底に留め、具象を書かないか(決定1)】
  情報処理基盤の構造 ── 値の型・統合・活性化・伝播、そして発達のさせ方 ── は **系統(§9.5)
  ごとに異なり、第 8 章の数学と一対一対応する**。したがってその具象は core に固定できない。
  core が約束するのは「発達ルールがこの箱をどう触れるか」という安定した仕組み(mechanism)
  だけであり、「いつ・どこを・どの確率で」という数学(§8)は `graphian.development` 側の
  具象 `Network` / `DevelopmentRule` が後続セッションで実装する。

  ゆえに本契約には伝播(propagate)・活性化(sigmoid/ReLU)・統合(加算)を **置かない**。
  `value`/`set_value` という素の器だけを露出する。

露出する仕組み(§5.1 / §7.2):
  - 構造の問い合わせ : geometry / has_node / neighbors(円をスキップした直結も許す)。
  - 構造の変異       : add/remove node・edge(両経路を §7.2-2 で一度は通す)。
                       追加はスロット容量を超えない(有界性 §5.1 / §9.7)。
  - 値               : value / set_value(更新規則=数学は持たない)。
  - 特別ノード・I/O  : reward_node(常に存在 §5.2)、接続点ノードの配置、接続点 I/O。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from graphian.core.buffer import ConnectionLayout, Snapshot
from graphian.core.geometry import Geometry, NodePosition


class Network(ABC):
    """発達対象の同心円グラフが満たす契約。具象は系統=§8(後続)で実装する。"""

    @property
    @abstractmethod
    def geometry(self) -> Geometry:
        """このネットワークが載る座標系(距離・角度・スロット容量を答える)。"""

    # --- 構造の問い合わせ(read) ---

    @abstractmethod
    def has_node(self, pos: NodePosition) -> bool:
        """`pos` にノードが存在するか。"""

    @abstractmethod
    def neighbors(self, pos: NodePosition) -> tuple[NodePosition, ...]:
        """`pos` に直結しているノード。大円↔小円が中間円をスキップした直結も含む(§5.1)。"""

    # --- 構造の変異(mechanism のみ。「いつ・どこを」は §8) ---

    @abstractmethod
    def add_node(self, pos: NodePosition) -> None:
        """ノードを追加する。スロット容量を超える追加は拒否する(有界性 §5.1/§9.7)。"""

    @abstractmethod
    def remove_node(self, pos: NodePosition) -> None:
        """ノードを削除する(関連エッジも除去)。"""

    @abstractmethod
    def add_edge(self, a: NodePosition, b: NodePosition) -> None:
        """エッジを追加する。初版は構造のみ。重み等の属性は §8 で引数追加され得る。"""

    @abstractmethod
    def remove_edge(self, a: NodePosition, b: NodePosition) -> None:
        """エッジを削除する。"""

    # --- 値(更新規則=活性化/統合/伝播は持たない。それは系統=§8) ---

    @abstractmethod
    def value(self, pos: NodePosition) -> float:
        """ノードの現在値([-1, +1] 想定)。"""

    @abstractmethod
    def set_value(self, pos: NodePosition, v: float) -> None:
        """ノードの値を設定する。"""

    # --- 特別ノードと接続点 I/O ---

    @property
    @abstractmethod
    def reward_node(self) -> NodePosition:
        """報酬系ノードの位置。常に存在する(消えない足場 §5.2)。値の算出元は §8。"""

    @abstractmethod
    def place_connection_nodes(self, layout: ConnectionLayout) -> None:
        """宣言された形(§3 ②)に従い、接続点ノードを直径 1 の専用円へ配置する(§7.2-1)。"""

    @abstractmethod
    def write_inputs(self, sensory: Snapshot) -> None:
        """感覚スナップショット(ENV_TO_PROC)を、対応する接続点ノードの値へ流し込む。"""

    @abstractmethod
    def read_outputs(self) -> Snapshot:
        """運動接続点ノード(PROC_TO_ENV)の値を、buffer へ送るスナップショットとして取り出す。"""

    # --- 永続化・可視化(§9.4 / §9.6) ---

    @abstractmethod
    def all_nodes(self) -> tuple[NodePosition, ...]:
        """現在存在するすべてのノードの位置を返す(スナップショット保存・描画用)。"""

    @abstractmethod
    def all_edges(self) -> tuple[tuple[NodePosition, NodePosition], ...]:
        """現在存在するすべてのエッジを (a, b) のペアで返す(スナップショット保存・描画用)。"""
