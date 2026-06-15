"""具象セッション実装(§5.4)。ダミー環境 + ダミー発達ルールで試行を一周回す(§11)。

クロックの独立性(§2.2):
  単一スレッドで A を clock_a_steps 回進めた後 B を clock_b_steps 回進める交互ループ。
  両者は InProcessConnectionBuffer 越しにしか通信しないため論理的に独立しており、
  clock_a_steps ≠ clock_b_steps で頻度比を非対称にできる(ロックステップ回避 §2.2)。
  将来の分散化時は Buffer の実体をネットワーク実装に差し替えるだけでよい(§2.3)。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from graphian.core.buffer import Flow, InProcessConnectionBuffer
from graphian.core.genome import BodyGenome, NetworkGenome
from graphian.core.geometry import NodePosition
from graphian.core.session import LineageRecord, PhylogeneticTree, Session, SessionConfig
from graphian.development.base import DevelopmentContext
from graphian.development.dummy import DummyDevelopmentRule, DummyNetwork, FixedBudget
from graphian.environments.phototaxis_1d import Phototaxis1DEnvironment
from graphian.persistence.logging_setup import EventLogger, get_event_logger, setup_logging
from graphian.persistence.snapshot import SnapshotWriter

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# 試行の実行(内部)
# ---------------------------------------------------------------------------


def _write_network_snapshot(
    writer: SnapshotWriter,
    network: DummyNetwork,
    conn_circle: int,
    trial: int,
    step: int,
) -> None:
    nodes = [
        {"c": p.circle, "s": p.slot, "v": round(network.value(p), 4)}
        for p in network.all_nodes()
    ]
    rn = network.reward_node
    edges = [
        {"from": {"c": a.circle, "s": a.slot}, "to": {"c": b.circle, "s": b.slot}}
        for a, b in network.all_edges()
    ]
    writer.write({
        "type": "network_snapshot",
        "trial": trial,
        "step": step,
        "conn_circle": conn_circle,
        "nodes": nodes,
        "edges": edges,
        "reward_node": {"c": rn.circle, "s": rn.slot},
    })


def _run_trial(
    *,
    net_genome: NetworkGenome,
    body_genome: BodyGenome,
    trial: int,
    x_light: float,
    max_steps: int,
    clock_a: int,
    clock_b: int,
    log_every: int,
    writer: SnapshotWriter,
    events: EventLogger,
) -> tuple[int, float, bool]:
    """1 試行を実行して (ステップ数, 適応度, 生存) を返す。"""
    # genome.seed から A・B の乱数を独立に作る(§5.2: 再現可能)。
    root = np.random.default_rng(net_genome.seed)
    seed_a, seed_b = root.integers(0, 2**31, size=2)
    rng_a = np.random.default_rng(int(seed_a))
    rng_b = np.random.default_rng(int(seed_b))

    buffer = InProcessConnectionBuffer()
    env = Phototaxis1DEnvironment(x_light=x_light)
    network = DummyNetwork(net_genome)
    budget = FixedBudget(n=max_steps * clock_b + 1000)
    ctx = DevelopmentContext(network=network, budget=budget, rng=rng_b)
    rule = DummyDevelopmentRule()

    # 初期化(§3 ①②)
    env.reset(body_genome, buffer, rng_a)
    rule.initialize(ctx, buffer.layout, net_genome)

    # 試行開始時のネットワークスナップショット
    _write_network_snapshot(writer, network, net_genome.num_circles, trial, 0)

    step = 0
    while step < max_steps and not env.is_done():
        # クロック A: clock_a 回進める
        for _ in range(clock_a):
            if env.is_done():
                break
            env.step()
            step += 1
            if step % log_every == 0:
                writer.write({
                    "type": "env_step",
                    "trial": trial,
                    "step": step,
                    "x": round(env.position, 4),
                    "energy": round(env.energy, 4),
                    "fitness_accum": round(env.fitness(), 4),
                    "alive": env.is_alive(),
                })

        if env.is_done():
            break

        # クロック B: clock_b 回進める
        sensory = buffer.read(Flow.ENV_TO_PROC)
        network.write_inputs(sensory)
        for _ in range(clock_b):
            rule.step(ctx)
        motor = network.read_outputs()
        buffer.write(Flow.PROC_TO_ENV, motor)

    # 試行終了時のネットワークスナップショット(最終状態)
    _write_network_snapshot(writer, network, net_genome.num_circles, trial, step)
    buffer.close()

    return step, env.fitness(), env.is_alive()


# ---------------------------------------------------------------------------
# 具象 Session
# ---------------------------------------------------------------------------


class SimpleSession(Session):
    """ダミー環境 + ダミー発達ルールを使う初版セッション(§5.4 / §11)。

    設定辞書(TOML を load_config で読んだもの)を受け取り、試行を回し、
    スナップショット・システムログ・事象ログを出力する。
    """

    def __init__(self) -> None:
        self._tree = PhylogeneticTree()

    # ------------------------------------------------------------------
    # Session 契約
    # ------------------------------------------------------------------

    def run(self, config: SessionConfig) -> None:
        raise NotImplementedError("SimpleSession.run_from_config を使うこと")

    def save(self, path: str) -> None:
        # §11 のスコープ内では run_from_config が随時保存するため、追加の save は不要。
        pass

    @classmethod
    def resume(cls, path: str) -> "SimpleSession":
        raise NotImplementedError("resume は後続フェーズで実装する(§11)")

    # ------------------------------------------------------------------
    # 実際のエントリポイント
    # ------------------------------------------------------------------

    def run_from_config(self, config: dict, output_dir: Path) -> Path:
        """TOML config dict からセッションを実行し、出力ディレクトリを返す。"""
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        sdir = output_dir / session_id
        sdir.mkdir(parents=True, exist_ok=True)

        # config のコピーを保存(再現性のため §9.4)
        import tomllib, copy
        cfg_copy = copy.deepcopy(config)
        (sdir / "config.json").write_text(
            json.dumps(cfg_copy, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        session_cfg = config.get("session", {})
        lineage_map = config.get("lineage", {})
        env_cfg = config.get("environment", {})
        out_cfg = config.get("output", {})

        lineage_name = next(iter(lineage_map))
        lconf = lineage_map[lineage_name]

        trials = int(session_cfg.get("trials", 5))
        max_steps = int(session_cfg.get("max_steps_per_trial", 1000))
        clock_a = int(session_cfg.get("clock_a_steps", 2))
        clock_b = int(session_cfg.get("clock_b_steps", 1))
        inherit_body = bool(session_cfg.get("inherit_body_genome", True))
        x_light = float(env_cfg.get("x_light", 0.5))
        log_every = max(1, max_steps // 50)  # ≈50 点/試行を記録

        events = setup_logging(sdir, out_cfg.get("log_level", "INFO"))

        with SnapshotWriter(sdir / "snapshot.jsonl") as writer:
            writer.write({
                "type": "session_start",
                "session_id": session_id,
                "config": cfg_copy,
                "timestamp": _now(),
            })
            events.log("session_start", session_id=session_id, trials=trials)

            # 初期 genome を config から構築
            slots = tuple(int(s) for s in lconf["slots_per_circle"])
            diams = tuple(float(d) for d in lconf["circle_diameters"])
            rc, rs = int(lconf.get("reward_circle", 0)), int(lconf.get("reward_slot", 0))
            seed = int(lconf["seed"])
            move_speed = float(lconf.get("move_speed", 0.2))

            net_genome = NetworkGenome(seed, slots, diams, NodePosition(rc, rs))
            body_genome = BodyGenome(seed, move_speed)
            genome_id = _short_id()

            # 系統樹のルートを記録
            self._tree.add(LineageRecord(genome_id, (), 0, lineage_name))
            writer.write({
                "type": "lineage",
                "genome_id": genome_id,
                "parent_ids": [],
                "generation": 0,
                "lineage_name": lineage_name,
            })

            for trial_no in range(trials):
                log.info("試行 %d/%d 開始 genome=%s", trial_no + 1, trials, genome_id)
                events.log("trial_start", trial=trial_no, genome_id=genome_id)
                writer.write({
                    "type": "trial_start",
                    "trial": trial_no,
                    "genome_id": genome_id,
                    "generation": trial_no,
                    "timestamp": _now(),
                })

                steps, fitness, alive = _run_trial(
                    net_genome=net_genome,
                    body_genome=body_genome,
                    trial=trial_no,
                    x_light=x_light,
                    max_steps=max_steps,
                    clock_a=clock_a,
                    clock_b=clock_b,
                    log_every=log_every,
                    writer=writer,
                    events=events,
                )

                result_word = "生存(満腹)" if alive else "死亡"
                log.info(
                    "試行 %d 終了: %s steps=%d fitness=%.3f",
                    trial_no, result_word, steps, fitness,
                )
                events.log(
                    "trial_end",
                    trial=trial_no,
                    alive=alive,
                    steps=steps,
                    fitness=round(fitness, 4),
                    genome_id=genome_id,
                )
                writer.write({
                    "type": "trial_end",
                    "trial": trial_no,
                    "fitness": round(fitness, 4),
                    "alive": alive,
                    "steps": steps,
                    "genome_id": genome_id,
                    "timestamp": _now(),
                })

                # genome 進化(§5.2: 変異で次世代の設計図を作る)
                evolve_rng = np.random.default_rng(net_genome.seed ^ (trial_no + 0xDEAD))
                parent_id = genome_id
                net_genome = net_genome.mutate(evolve_rng)
                body_genome = (
                    body_genome.mutate(evolve_rng) if inherit_body
                    else BodyGenome(seed, move_speed)
                )
                genome_id = _short_id()

                self._tree.add(
                    LineageRecord(genome_id, (parent_id,), trial_no + 1, lineage_name)
                )
                writer.write({
                    "type": "lineage",
                    "genome_id": genome_id,
                    "parent_ids": [parent_id],
                    "generation": trial_no + 1,
                    "lineage_name": lineage_name,
                })

            writer.write({
                "type": "session_end",
                "session_id": session_id,
                "trials_completed": trials,
                "timestamp": _now(),
            })
            events.log("session_end", session_id=session_id, trials_completed=trials)

        events.close()
        log.info("セッション保存先: %s", sdir)
        return sdir
