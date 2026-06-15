"""同心円構造の幾何(§5.1)。

`Geometry` は genome から構築される **状態を持たない純粋計算**(座標系という定規)であり、
「位置 → 距離 / 角度」を答える。ここには発達ルールの数学(§8)は一切含まない。

設計上の固定点(§5.1):
  - ノードの位置は **(どの円, どのスロット)** の整数ペア `NodePosition` で一意に定まる。
  - 角度は離散スロット。連続値にしない ── 同一ノード判定が整数比較で確定し、
    浮動小数点誤差に挙動が支配されず、整数ペアでテキスト保存=完全再現可能になる。
  - 円ごとにスロット数を変える(スロット数は genome 由来 §5.2)。
  - 各円の直径は最大 1(直径も genome 由来 §5.2/決定3)。ゆえにノード間距離の最大値は 1。

接続点専用の直径 1 の円(§5.1 末)は、layout に応じてスロットが決まるため `Geometry` では
扱わず、`graphian.core.network.Network.place_connection_nodes` の責務とする。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NodePosition:
    """ノードの一意な位置 ── (どの円, どのスロット) の整数ペア(§5.1)。

    不変かつハッシュ可能。これにより「同一ノードか否か」の判定が整数比較で確定し、
    集合/辞書のキー(=ノード同一性の担い手)として使える。
    """

    circle: int
    slot: int


class Geometry:
    """同心円の幾何。`from_circles` で genome 由来のスロット数・直径から構築する。

    内部は半径(=直径/2)で保持する。距離計算に登場するのは半径であり(§5.1)、
    直径の最大が 1 ゆえ半径の最大は 0.5、2 点間距離の最大は 1 になる。
    """

    __slots__ = ("_slots", "_radii")

    def __init__(self, slots_per_circle: tuple[int, ...], radii: tuple[float, ...]) -> None:
        # 直接の生成は避け、検証付きの `from_circles` を使うこと。
        self._slots = tuple(slots_per_circle)
        self._radii = tuple(radii)

    @classmethod
    def from_circles(
        cls,
        slots_per_circle: tuple[int, ...],
        circle_diameters: tuple[float, ...],
    ) -> "Geometry":
        """スロット数列と直径列(ともに genome 由来)から幾何を構築する。

        検証(明快なエラーを優先 §9.3):
          - 両列の長さが一致し、円が 1 つ以上あること。
          - 各スロット数 >= 1。
          - 各直径が (0, 1] に入る(§5.1: 直径は最大 1)。
        """
        slots = tuple(int(s) for s in slots_per_circle)
        diameters = tuple(float(d) for d in circle_diameters)
        if len(slots) != len(diameters):
            raise ValueError(
                f"slots_per_circle と circle_diameters の長さが異なる: "
                f"{len(slots)} != {len(diameters)}"
            )
        if len(slots) == 0:
            raise ValueError("円が 1 つ以上必要")
        for i, s in enumerate(slots):
            if s < 1:
                raise ValueError(f"円 {i} のスロット数は 1 以上でなければならない: {s}")
        for i, d in enumerate(diameters):
            if not (0.0 < d <= 1.0):
                raise ValueError(f"円 {i} の直径は (0, 1] に入る必要がある: {d}")
        radii = tuple(d / 2.0 for d in diameters)
        return cls(slots, radii)

    @property
    def num_circles(self) -> int:
        """円の数。"""
        return len(self._slots)

    def slots_in(self, circle: int) -> int:
        """指定した円のスロット数。"""
        return self._slots[circle]

    def radius_of(self, circle: int) -> float:
        """指定した円の半径(= 直径 / 2、最大 0.5)。"""
        return self._radii[circle]

    def contains(self, pos: NodePosition) -> bool:
        """`pos` がこの幾何の有効な位置(円・スロットが範囲内)か。"""
        return 0 <= pos.circle < len(self._slots) and 0 <= pos.slot < self._slots[pos.circle]

    def angle_of(self, pos: NodePosition) -> float:
        """スロット番号を角度(ラジアン)へ変換する。

        スロット(整数=同一性の担い手)と角度(float=空間計算)を意図的に分離し、
        距離計算のときだけ角度に変換する(§5.1 の使い分け)。
        """
        return 2.0 * math.pi * pos.slot / self._slots[pos.circle]

    def distance(self, a: NodePosition, b: NodePosition) -> float:
        """2 ノード間のユークリッド距離。戻り値は必ず [0, 1] に収まる(§5.1)。

        各ノードを極座標 (半径, 角度) とみなし、同一平面上の 2 点間距離として計算する。
        距離は §8 の接続確率式 `P = p_max * exp(-d^2 / sigma^2)` の入力になる量で、
        値域が固定であること自体が数学設計の前提になるため、ここで [0, 1] にクランプする。
        """
        ra = self._radii[a.circle]
        rb = self._radii[b.circle]
        theta = self.angle_of(a) - self.angle_of(b)
        # 余弦定理。数学的には >= 0 だが浮動小数で僅かに負になり得るため 0 で下限を切る。
        squared = ra * ra + rb * rb - 2.0 * ra * rb * math.cos(theta)
        d = math.sqrt(squared) if squared > 0.0 else 0.0
        if d > 1.0:  # 半径 <= 0.5 ゆえ理論上 <= 1。誤差分のみクランプ。
            return 1.0
        return d
