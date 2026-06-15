"""genome の変異・配合テスト(§9.10)。

1. 決定論的な単体テスト : 検証・永続化ラウンドトリップ・変異の決定性・片親コピーが仕様どおりか。
2. 不変条件テスト(Hypothesis): 変異後も genome が妥当(スロット>=1・直径∈(0,1]・報酬位置が有効)
   か、配合結果が必ず親のいずれかと一致するか、変異が決定的か。
"""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from graphian.core.genome import (
    BodyGenome,
    NetworkGenome,
    crossover,
    genome_from_record,
)
from graphian.core.geometry import NodePosition


def _net(seed: int = 1) -> NetworkGenome:
    return NetworkGenome(seed, (4, 8), (0.5, 1.0), NodePosition(1, 3))


# ---------------------------------------------------------------------------
# 1. 決定論的な単体テスト
# ---------------------------------------------------------------------------


def test_network_genome_valid():
    g = _net()
    assert g.num_circles == 2


def test_network_genome_rejects_bad_slot():
    with pytest.raises(ValueError):
        NetworkGenome(1, (0,), (1.0,), NodePosition(0, 0))


def test_network_genome_rejects_diameter_over_one():
    with pytest.raises(ValueError):
        NetworkGenome(1, (4,), (1.5,), NodePosition(0, 0))


def test_network_genome_rejects_reward_slot_out_of_range():
    with pytest.raises(ValueError):
        NetworkGenome(1, (4,), (1.0,), NodePosition(0, 9))


def test_network_genome_rejects_reward_circle_out_of_range():
    with pytest.raises(ValueError):
        NetworkGenome(1, (4,), (1.0,), NodePosition(5, 0))


def test_network_genome_rejects_length_mismatch():
    with pytest.raises(ValueError):
        NetworkGenome(1, (4, 8), (1.0,), NodePosition(0, 0))


def test_body_genome_rejects_negative_speed():
    with pytest.raises(ValueError):
        BodyGenome(1, -0.5)


def test_record_roundtrip_network():
    g = _net(7)
    assert genome_from_record(g.to_record()) == g


def test_record_roundtrip_body():
    g = BodyGenome(3, 0.7)
    assert genome_from_record(g.to_record()) == g


def test_mutate_is_deterministic():
    g = _net()
    assert g.mutate(np.random.default_rng(42)) == g.mutate(np.random.default_rng(42))


def test_mutate_changes_seed():
    # 変異はシードを必ず変える ── 異なる rng ストリームでは別の genome になる。
    g = _net()
    a = g.mutate(np.random.default_rng(1))
    b = g.mutate(np.random.default_rng(2))
    assert a != b


def test_mutate_returns_new_object_leaving_original():
    g = _net()
    _ = g.mutate(np.random.default_rng(0))
    assert g == _net()  # 元は不変


def test_crossover_is_single_parent_copy():
    a, b = _net(1), _net(2)
    child = crossover(a, b, np.random.default_rng(0))
    assert child == a or child == b


def test_crossover_rejects_mixed_types():
    with pytest.raises(TypeError):
        crossover(_net(), BodyGenome(1, 0.5), np.random.default_rng(0))


# ---------------------------------------------------------------------------
# 2. 不変条件テスト(property-based / Hypothesis)
# ---------------------------------------------------------------------------


@st.composite
def network_genomes(draw) -> NetworkGenome:
    """妥当な NetworkGenome を生成する(報酬系位置は構造に整合させる)。"""
    n = draw(st.integers(min_value=1, max_value=5))
    slots = draw(st.lists(st.integers(min_value=1, max_value=8), min_size=n, max_size=n))
    diameters = draw(
        st.lists(
            st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rc = draw(st.integers(min_value=0, max_value=n - 1))
    rs = draw(st.integers(min_value=0, max_value=slots[rc] - 1))
    return NetworkGenome(seed, tuple(slots), tuple(diameters), NodePosition(rc, rs))


@given(network_genomes(), st.integers(min_value=0, max_value=2**31 - 1))
def test_mutate_preserves_invariants(g, seed):
    m = g.mutate(np.random.default_rng(seed))
    assert m.num_circles == g.num_circles  # 円数は保存
    assert all(s >= 1 for s in m.slots_per_circle)
    assert all(0.0 < d <= 1.0 for d in m.circle_diameters)
    assert 0 <= m.reward_node.circle < m.num_circles
    assert 0 <= m.reward_node.slot < m.slots_per_circle[m.reward_node.circle]


@given(network_genomes())
def test_network_record_roundtrip(g):
    assert genome_from_record(g.to_record()) == g


@given(network_genomes(), network_genomes(), st.integers(min_value=0, max_value=2**31 - 1))
def test_crossover_returns_a_parent(a, b, seed):
    child = crossover(a, b, np.random.default_rng(seed))
    assert child == a or child == b


@given(network_genomes(), st.integers(min_value=0, max_value=2**31 - 1))
def test_mutate_deterministic_property(g, seed):
    assert g.mutate(np.random.default_rng(seed)) == g.mutate(np.random.default_rng(seed))
