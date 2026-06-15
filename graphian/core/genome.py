"""遺伝子(§5.2)。

genome は「ネットワークがどう発達するか」を定める設計図であり、世代を超えて継承されるのは
これ(=設計図)であって発達した結果ではない(§0)。**不変な値オブジェクト**として実装する
ことを契約とする ── 各 genome は系統追跡と再現性の単位(改変不能なスナップショット)になる。

ここに置くのは genome の **表現と進化機構(変異・配合)** のみ(§5.2)。これらは進化の機構で
あって発達ルールの数学(§8)ではないため core に置いてよい。ただし「スロット数・報酬系位置の
異なる親同士のブレンド配合」は未確定であり(§8)、初版の配合は **片親コピー** に留める。

すべての確率的挙動は genome の乱数シードから取る(§5.2)。同じ genome なら挙動が再現し、
違えば異なる ── これにより継承・配合・変異が骨格レベルで検証可能になる。
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from graphian.core.geometry import NodePosition

# 変異後も直径を (0, 1] に保つための下限(§5.1: 直径は最大 1、0 は不可)。
_DIAMETER_MIN = 1e-3
# 変異後も移動速度係数を正に保つための下限(§7.1)。
_SPEED_MIN = 1e-3
# 乱数シードの上限(再現可能・テキスト保存可能な範囲)。
_SEED_MAX = 2**31 - 1


class Genome(ABC):
    """全 genome が満たす契約。

    すべての具象 genome は ``seed: int`` を持ち(契約: 全確率的挙動の源 §5.2)、変異・
    永続化の機構を共有する。`mutate` は **新しい genome を返す**(self は不変)。
    """

    # 契約: 全 genome は乱数シードを持つ。abstractmethod にはせず、各具象 dataclass の
    # フィールドとして実体化する(アノテーションは契約の明示)。
    seed: int

    @abstractmethod
    def mutate(self, rng: np.random.Generator) -> "Genome":
        """変異を 1 回適用した新しい genome を返す。元の genome は変更しない。"""

    @abstractmethod
    def to_record(self) -> dict:
        """テキスト永続化(JSONL §9.4)用の辞書へ変換する。"""

    @classmethod
    @abstractmethod
    def from_record(cls, data: dict) -> "Genome":
        """`to_record` の逆。読込→保存が完全再現可能であること(§5.1)。"""


@dataclass(frozen=True, slots=True)
class NetworkGenome(Genome):
    """情報処理系ネットワークの発達を定める genome(§5.2)。

    フィールド:
      - ``seed``              : 乱数シード。
      - ``slots_per_circle``  : 円ごとのスロット数(§5.1)。
      - ``circle_diameters``  : 円ごとの直径。各 (0, 1](決定3: 直径も遺伝子に含める)。
      - ``reward_node``       : 報酬系ノードの位置。存在は固定(消えない足場)だが、位置は
                                genome が規定し進化が探索する。初版は 1 つ(§5.2/§8)。

    発達ルール本体のパラメータは §8 で本クラスにフィールド追加される(契約は据置)。
    """

    seed: int
    slots_per_circle: tuple[int, ...]
    circle_diameters: tuple[float, ...]
    reward_node: NodePosition

    def __post_init__(self) -> None:
        n = len(self.slots_per_circle)
        if n == 0:
            raise ValueError("円が 1 つ以上必要")
        if len(self.circle_diameters) != n:
            raise ValueError(
                f"slots_per_circle と circle_diameters の長さが異なる: "
                f"{n} != {len(self.circle_diameters)}"
            )
        if any(s < 1 for s in self.slots_per_circle):
            raise ValueError(f"各スロット数は 1 以上: {self.slots_per_circle}")
        if any(not (0.0 < d <= 1.0) for d in self.circle_diameters):
            raise ValueError(f"各直径は (0, 1]: {self.circle_diameters}")
        rc, rs = self.reward_node.circle, self.reward_node.slot
        if not (0 <= rc < n):
            raise ValueError(f"報酬系ノードの円が範囲外: {rc} (円数 {n})")
        if not (0 <= rs < self.slots_per_circle[rc]):
            raise ValueError(
                f"報酬系ノードのスロットが範囲外: {rs} (円 {rc} のスロット数 "
                f"{self.slots_per_circle[rc]})"
            )

    @property
    def num_circles(self) -> int:
        return len(self.slots_per_circle)

    def mutate(self, rng: np.random.Generator) -> "NetworkGenome":
        """シードを必ず変え、構造(スロット数・直径)を小さく揺らし、報酬系位置を探索する。

        初版は骨格検証に足る最小の変異に留める(変異幅などのチューニングは後続 §8)。
        円の増減は構造の大変化のため初版では行わない(円数は保存)。
        """
        new_seed = int(rng.integers(0, _SEED_MAX))
        # スロット数を各円 -1/0/+1(1 未満にはしない)。
        new_slots = tuple(
            max(1, s + int(rng.integers(-1, 2))) for s in self.slots_per_circle
        )
        # 直径に小さな正規ノイズを与え (0, 1] にクランプ。
        new_diameters = tuple(
            float(min(1.0, max(_DIAMETER_MIN, d + rng.normal(0.0, 0.1))))
            for d in self.circle_diameters
        )
        # 報酬系ノード: 円数は不変なので円はそのまま有効。スロットは確率で再サンプル、
        # さもなくばスロット数減少に備えてクランプ(§5.2: 位置を進化が探索)。
        rc = self.reward_node.circle
        if rng.random() < 0.25:
            rs = int(rng.integers(0, new_slots[rc]))
        else:
            rs = min(self.reward_node.slot, new_slots[rc] - 1)
        return NetworkGenome(new_seed, new_slots, new_diameters, NodePosition(rc, rs))

    def to_record(self) -> dict:
        return {
            "type": "NetworkGenome",
            "seed": self.seed,
            "slots_per_circle": list(self.slots_per_circle),
            "circle_diameters": list(self.circle_diameters),
            "reward_node": {"circle": self.reward_node.circle, "slot": self.reward_node.slot},
        }

    @classmethod
    def from_record(cls, data: dict) -> "NetworkGenome":
        rn = data["reward_node"]
        return cls(
            seed=int(data["seed"]),
            slots_per_circle=tuple(int(s) for s in data["slots_per_circle"]),
            circle_diameters=tuple(float(d) for d in data["circle_diameters"]),
            reward_node=NodePosition(int(rn["circle"]), int(rn["slot"])),
        )


@dataclass(frozen=True, slots=True)
class BodyGenome(Genome):
    """身体側の genome(§7.1)。初版はほぼ空で、移動速度の係数を 1 つだけ持つ。

    身体側の進化・配合・継承経路を一度起動させるための最小フィールド。body genome は
    情報処理系 genome と同じ機構(本モジュール)に乗る(§5.2/§7.1)。
    """

    seed: int
    move_speed: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.move_speed):
            raise ValueError(f"move_speed は有限値: {self.move_speed}")
        if self.move_speed < 0.0:
            raise ValueError(f"move_speed は 0 以上: {self.move_speed}")

    def mutate(self, rng: np.random.Generator) -> "BodyGenome":
        new_seed = int(rng.integers(0, _SEED_MAX))
        new_speed = float(max(_SPEED_MIN, self.move_speed + rng.normal(0.0, 0.1)))
        return BodyGenome(new_seed, new_speed)

    def to_record(self) -> dict:
        return {"type": "BodyGenome", "seed": self.seed, "move_speed": self.move_speed}

    @classmethod
    def from_record(cls, data: dict) -> "BodyGenome":
        return cls(seed=int(data["seed"]), move_speed=float(data["move_speed"]))


def crossover(a: Genome, b: Genome, rng: np.random.Generator) -> Genome:
    """配合機構(§5.2)。初版は **片親コピー** ── どちらかの親を丸ごと採用する。

    genome は不変なので、選んだ親をそのまま返してよい。結果は必ず親のいずれかと等価
    (この不変条件が §9.10 のテストで検証される)。スロット数・報酬系位置の異なる親同士の
    ブレンド配合は未確定であり後続(§8)で詰めるが、シグネチャは据え置く。
    """
    if type(a) is not type(b):
        raise TypeError(
            f"crossover は同じ型の genome 同士に限る: {type(a).__name__} と {type(b).__name__}"
        )
    return a if rng.random() < 0.5 else b


_REGISTRY: dict[str, type[Genome]] = {
    "NetworkGenome": NetworkGenome,
    "BodyGenome": BodyGenome,
}


def genome_from_record(data: dict) -> Genome:
    """`to_record` が書いた辞書から、型タグ(``"type"``)に応じて genome を復元する。"""
    type_name = data["type"]
    if type_name not in _REGISTRY:
        raise ValueError(f"未知の genome 型: {type_name!r}")
    return _REGISTRY[type_name].from_record(data)
