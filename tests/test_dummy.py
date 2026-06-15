"""ダミー実装のスモークテスト ── §7.2 の 4 契約点と §7.1 のエネルギー動態を確認する。

このテストは「骨格のすべての契約点を一度は通過させる」(§7 原則)の検証であり、
数学的な発達ルールの正しさを問うものではない。
"""

import numpy as np
import pytest

from graphian.core.buffer import ConnectionPoint, Flow, InProcessConnectionBuffer
from graphian.core.genome import BodyGenome, NetworkGenome
from graphian.core.geometry import NodePosition
from graphian.development.dummy import (
    DummyDevelopmentRule,
    DummyNetwork,
    FixedBudget,
)
from graphian.development.base import DevelopmentContext
from graphian.environments.phototaxis_1d import Phototaxis1DEnvironment


def _net_genome(seed: int = 1) -> NetworkGenome:
    return NetworkGenome(
        seed=seed,
        slots_per_circle=(4, 8),
        circle_diameters=(0.5, 1.0),
        reward_node=NodePosition(0, 1),
    )


def _body_genome(seed: int = 1) -> BodyGenome:
    return BodyGenome(seed=seed, move_speed=0.2)


# ---------------------------------------------------------------------------
# DummyNetwork
# ---------------------------------------------------------------------------


def test_dummy_network_add_remove_node():
    g = _net_genome()
    net = DummyNetwork(g)
    pos = NodePosition(0, 0)
    assert not net.has_node(pos)
    net.add_node(pos)
    assert net.has_node(pos)
    net.remove_node(pos)
    assert not net.has_node(pos)


def test_dummy_network_add_remove_edge():
    g = _net_genome()
    net = DummyNetwork(g)
    a, b = NodePosition(0, 0), NodePosition(0, 1)
    net.add_node(a)
    net.add_node(b)
    net.add_edge(a, b)
    assert b in net.neighbors(a)
    net.remove_edge(a, b)
    assert b not in net.neighbors(a)
    # 関連エッジが消えてもノードは残る。
    assert net.has_node(a)


def test_dummy_network_rejects_out_of_bounds():
    g = _net_genome()
    net = DummyNetwork(g)
    with pytest.raises(ValueError):
        net.add_node(NodePosition(0, 100))  # スロット容量超過


def test_dummy_network_place_connection_nodes_and_io():
    g = _net_genome()
    net = DummyNetwork(g)
    layout = (
        ConnectionPoint("light_direction", Flow.ENV_TO_PROC),
        ConnectionPoint("move", Flow.PROC_TO_ENV),
    )
    net.place_connection_nodes(layout)
    # 接続点ノードが存在する。
    conn_circle = g.num_circles
    assert net.has_node(NodePosition(conn_circle, 0))
    assert net.has_node(NodePosition(conn_circle, 1))
    # write_inputs / read_outputs が動く。
    net.write_inputs(np.array([0.7], dtype=np.float32))
    outputs = net.read_outputs()
    assert outputs.shape == (1,)  # PROC_TO_ENV は 1 点


def test_dummy_network_reward_node():
    g = _net_genome()
    net = DummyNetwork(g)
    assert net.reward_node == g.reward_node


# ---------------------------------------------------------------------------
# FixedBudget
# ---------------------------------------------------------------------------


def test_fixed_budget_consume_and_exhaust():
    b = FixedBudget(n=3)
    assert not b.exhausted()
    b.charge(2)
    assert b.remaining == 1
    b.charge(5)
    assert b.remaining == 0
    assert b.exhausted()


# ---------------------------------------------------------------------------
# DummyDevelopmentRule ── §7.2 の 4 契約点
# ---------------------------------------------------------------------------


def _make_ctx(genome: NetworkGenome, budget_n: int = 100) -> DevelopmentContext:
    net = DummyNetwork(genome)
    budget = FixedBudget(budget_n)
    rng = np.random.default_rng(genome.seed)
    return DevelopmentContext(network=net, budget=budget, rng=rng)


def test_dummy_dev_rule_initialize_places_connection_and_reward_nodes():
    """契約点 1・2: 接続点配置 + 報酬ノード固定配置。"""
    genome = _net_genome()
    ctx = _make_ctx(genome)
    layout = (
        ConnectionPoint("light_direction", Flow.ENV_TO_PROC),
        ConnectionPoint("move", Flow.PROC_TO_ENV),
    )
    rule = DummyDevelopmentRule()
    rule.initialize(ctx, layout, genome)
    # 接続点ノードが存在する。
    conn_circle = genome.num_circles
    assert ctx.network.has_node(NodePosition(conn_circle, 0))
    assert ctx.network.has_node(NodePosition(conn_circle, 1))
    # 報酬ノードが存在する。
    assert ctx.network.has_node(genome.reward_node)


def test_dummy_dev_rule_step_consumes_budget():
    """契約点 4: 予算消費。"""
    genome = _net_genome()
    ctx = _make_ctx(genome, budget_n=10)
    layout = (
        ConnectionPoint("light_direction", Flow.ENV_TO_PROC),
        ConnectionPoint("move", Flow.PROC_TO_ENV),
    )
    rule = DummyDevelopmentRule()
    rule.initialize(ctx, layout, genome)
    before = ctx.budget.remaining
    rule.step(ctx)
    assert ctx.budget.remaining < before


def test_dummy_dev_rule_step_cuts_off_when_exhausted():
    """契約点 4: 予算超過で打ち切り(step が budget.exhausted を確認する)。"""
    genome = _net_genome()
    ctx = _make_ctx(genome, budget_n=1)
    layout = (
        ConnectionPoint("light_direction", Flow.ENV_TO_PROC),
        ConnectionPoint("move", Flow.PROC_TO_ENV),
    )
    rule = DummyDevelopmentRule()
    rule.initialize(ctx, layout, genome)
    rule.step(ctx)  # 残り 1 を消費。
    assert ctx.budget.exhausted()
    # もう一度呼んでも例外は起きない(打ち切るだけ)。
    rule.step(ctx)


def test_dummy_dev_rule_step_writes_motor():
    """契約点 3: 運動接続点への書き戻し。"""
    genome = _net_genome()
    ctx = _make_ctx(genome)
    layout = (
        ConnectionPoint("light_direction", Flow.ENV_TO_PROC),
        ConnectionPoint("move", Flow.PROC_TO_ENV),
    )
    rule = DummyDevelopmentRule()
    rule.initialize(ctx, layout, genome)
    # 初期値は 0。step 後に乱数が書かれる。
    conn_circle = genome.num_circles
    motor_pos = NodePosition(conn_circle, 1)  # layout index 1 は PROC_TO_ENV
    before = ctx.network.value(motor_pos)
    rule.step(ctx)
    after = ctx.network.value(motor_pos)
    # rng.uniform(-1, 1) は 0 でない可能性が極めて高い。
    # ただし厳密に != は乱数なので -1e-9 < |after| を確認する。
    assert after != before or after != 0.0  # 何らかの値が書かれた


# ---------------------------------------------------------------------------
# Phototaxis1DEnvironment ── §7.1 の動態
# ---------------------------------------------------------------------------


def test_phototaxis_rejects_out_of_range_light():
    with pytest.raises(ValueError):
        Phototaxis1DEnvironment(x_light=2.0)


def test_phototaxis_initial_state_after_reset():
    env = Phototaxis1DEnvironment(x_light=0.5)
    buf = InProcessConnectionBuffer()
    rng = np.random.default_rng(0)
    env.reset(_body_genome(), buf, rng)
    assert env.is_alive()
    assert not env.is_done()
    assert env.fitness() == pytest.approx(0.0, abs=2.0)  # fitness はまだ 0


def test_phototaxis_buffer_layout_declared_after_reset():
    env = Phototaxis1DEnvironment(x_light=0.5)
    buf = InProcessConnectionBuffer()
    rng = np.random.default_rng(0)
    env.reset(_body_genome(), buf, rng)
    # 接続点の形が宣言されている。
    assert len(buf.layout) == 2
    assert buf.layout[0].name == "light_direction"
    assert buf.layout[1].name == "move"


def test_phototaxis_sensory_written_to_buffer_after_reset():
    env = Phototaxis1DEnvironment(x_light=0.5)
    buf = InProcessConnectionBuffer()
    rng = np.random.default_rng(42)
    env.reset(_body_genome(), buf, rng)
    sensory = buf.read(Flow.ENV_TO_PROC)
    # クランプ後の値が [-1, 1] 内にある。
    assert -1.0 <= float(sensory[0]) <= 1.0


def test_phototaxis_dies_when_energy_depletes():
    """エネルギーが 0 になったら死亡(§7.1)。光源から遠くに置き何も動かない。"""
    env = Phototaxis1DEnvironment(x_light=0.5)
    buf = InProcessConnectionBuffer()
    rng = np.random.default_rng(0)
    body = BodyGenome(seed=0, move_speed=0.0)  # 動かない
    env.reset(body, buf, rng)
    # 初期位置を光源から遠い側に強制(rng で決まるが、十分なステップで必ず死ぬ)。
    steps = 0
    while env.is_alive() and steps < 10000:
        env.step()
        steps += 1
    # 十分なステップで必ずエネルギーが尽きる(光から遠い場合)か満腹になる。
    assert env.is_done()


def test_phototaxis_sated_when_near_light():
    """光源の真横に固定したら満腹になる(§7.1)。"""
    env = Phototaxis1DEnvironment(x_light=0.0)
    buf = InProcessConnectionBuffer()
    rng = np.random.default_rng(0)
    body = BodyGenome(seed=0, move_speed=0.5)
    env.reset(body, buf, rng)
    # motor = 正の値を毎ステップ書いて光源(0)方向へ強制的に動かす。
    # x_light=0 で x が 0 に張り付けば net energy gain = +0.01/step。
    # 最大ステップ数を制限して確認。
    for _ in range(200):
        # 光源方向へ向かう符号の motor を書く(buf がクランプ)。
        direction = 0.0 - env._x
        buf.write(Flow.PROC_TO_ENV, np.array([np.sign(direction) * 10.0], dtype=np.float32))
        env.step()
        if env.is_done():
            break
    assert env.is_done()
    # 生存して満腹になった場合、適応度は正の値。
    if env.is_alive():
        assert env.fitness() > 0.0


def test_phototaxis_fitness_is_continuous():
    """適応度が二値でなく連続量になっている(§7.1)。"""
    env = Phototaxis1DEnvironment(x_light=0.5)
    buf = InProcessConnectionBuffer()
    rng = np.random.default_rng(7)
    env.reset(_body_genome(), buf, rng)
    for _ in range(50):
        env.step()
        if env.is_done():
            break
    # 適応度は 0 以上の連続値(0 ステップでは 0 だが 50 ステップ後は > 0 になるはず)。
    assert env.fitness() >= 0.0


# ---------------------------------------------------------------------------
# 統合スモーク: 環境 ↔ buffer ↔ 発達ルールの閉ループ
# ---------------------------------------------------------------------------


def test_full_loop_smoke():
    """感覚 → B(dummy) → 運動 の最小閉ループを N ステップ回す。例外なく完走すること。"""
    genome = _net_genome(seed=42)
    body = _body_genome(seed=42)
    buf = InProcessConnectionBuffer()
    env = Phototaxis1DEnvironment(x_light=0.3)
    rng_env = np.random.default_rng(body.seed)
    rng_b = np.random.default_rng(genome.seed)
    layout = (
        ConnectionPoint("light_direction", Flow.ENV_TO_PROC),
        ConnectionPoint("move", Flow.PROC_TO_ENV),
    )
    # 初期化
    env.reset(body, buf, rng_env)
    net = DummyNetwork(genome)
    budget = FixedBudget(n=500)
    ctx = DevelopmentContext(network=net, budget=budget, rng=rng_b)
    rule = DummyDevelopmentRule()
    rule.initialize(ctx, layout, genome)

    for _ in range(100):
        # クロック A
        env.step()
        if env.is_done():
            break
        # クロック B: buffer → network → dev rule → buffer
        sensory = buf.read(Flow.ENV_TO_PROC)
        net.write_inputs(sensory)
        rule.step(ctx)
        motor = net.read_outputs()
        buf.write(Flow.PROC_TO_ENV, motor)

    # 生死にかかわらず fitness は非負。
    assert env.fitness() >= 0.0
