"""geometry の距離計算テスト(§9.10)。

1. 決定論的な単体テスト : 既知の座標・距離・角度が仕様どおりか。
2. 不変条件テスト(Hypothesis): 距離が必ず [0, 1] に収まるか、対称か、三角不等式を満たすか。
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from graphian.core.geometry import Geometry, NodePosition

# ---------------------------------------------------------------------------
# 1. 決定論的な単体テスト
# ---------------------------------------------------------------------------


def test_distance_same_node_is_zero():
    g = Geometry.from_circles((4,), (1.0,))
    assert g.distance(NodePosition(0, 0), NodePosition(0, 0)) == 0.0


def test_distance_opposite_on_unit_circle_is_one():
    # 直径 1 の円の対極(スロット 0 と 2、半周)は距離 1(= 直径)。距離の最大値(§5.1)。
    g = Geometry.from_circles((4,), (1.0,))
    assert g.distance(NodePosition(0, 0), NodePosition(0, 2)) == pytest.approx(1.0)


def test_distance_quarter_turn():
    # 直径 1(半径 0.5)の円上、90度差: sqrt(0.5^2 + 0.5^2) = sqrt(0.5)。
    g = Geometry.from_circles((4,), (1.0,))
    assert g.distance(NodePosition(0, 0), NodePosition(0, 1)) == pytest.approx(math.sqrt(0.5))


def test_distance_between_circles_same_angle():
    # 同一角度・異なる円(半径 0.25 と 0.5)は半径差 = 0.25。
    g = Geometry.from_circles((4, 4), (0.5, 1.0))
    assert g.distance(NodePosition(0, 0), NodePosition(1, 0)) == pytest.approx(0.25)


def test_angle_of_quarter():
    g = Geometry.from_circles((4,), (1.0,))
    assert g.angle_of(NodePosition(0, 1)) == pytest.approx(math.pi / 2)


def test_contains():
    g = Geometry.from_circles((4, 8), (0.5, 1.0))
    assert g.contains(NodePosition(1, 7))
    assert not g.contains(NodePosition(1, 8))
    assert not g.contains(NodePosition(2, 0))
    assert not g.contains(NodePosition(0, -1))


def test_from_circles_rejects_bad_slot():
    with pytest.raises(ValueError):
        Geometry.from_circles((0,), (1.0,))


def test_from_circles_rejects_diameter_over_one():
    with pytest.raises(ValueError):
        Geometry.from_circles((4,), (1.5,))


def test_from_circles_rejects_diameter_zero():
    with pytest.raises(ValueError):
        Geometry.from_circles((4,), (0.0,))


def test_from_circles_rejects_length_mismatch():
    with pytest.raises(ValueError):
        Geometry.from_circles((4, 8), (1.0,))


def test_from_circles_rejects_empty():
    with pytest.raises(ValueError):
        Geometry.from_circles((), ())


# ---------------------------------------------------------------------------
# 2. 不変条件テスト(property-based / Hypothesis)
# ---------------------------------------------------------------------------


@st.composite
def geometries_with_positions(draw, n_positions: int = 2):
    """妥当な Geometry と、その上の `n_positions` 個の有効なノード位置を生成する。"""
    n = draw(st.integers(min_value=1, max_value=5))
    slots = draw(st.lists(st.integers(min_value=1, max_value=8), min_size=n, max_size=n))
    diameters = draw(
        st.lists(
            st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    geometry = Geometry.from_circles(tuple(slots), tuple(diameters))
    positions = []
    for _ in range(n_positions):
        c = draw(st.integers(min_value=0, max_value=n - 1))
        s = draw(st.integers(min_value=0, max_value=slots[c] - 1))
        positions.append(NodePosition(c, s))
    return geometry, positions


@given(geometries_with_positions())
def test_distance_within_unit_range(data):
    geometry, (a, b) = data
    d = geometry.distance(a, b)
    assert 0.0 <= d <= 1.0


@given(geometries_with_positions())
def test_distance_is_symmetric(data):
    geometry, (a, b) = data
    assert geometry.distance(a, b) == pytest.approx(geometry.distance(b, a))


@given(geometries_with_positions())
def test_distance_to_self_is_zero(data):
    geometry, (a, _b) = data
    assert geometry.distance(a, a) == 0.0


@given(geometries_with_positions(n_positions=3))
def test_distance_triangle_inequality(data):
    geometry, (a, b, c) = data
    # ユークリッド距離なので必ず成立。浮動小数誤差分のみ許容。
    assert geometry.distance(a, c) <= geometry.distance(a, b) + geometry.distance(b, c) + 1e-9
