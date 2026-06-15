"""JSONL スナップショットの読み書きと、可視化用への変換(§9.4)。

スナップショットは節目(試行の区切り等)で保存する。1 行 1 レコードの JSONL。
diff が取りやすく人間可読であること(§9.4)を優先し、バイナリは使わない。

レコードの type 一覧:
  session_start   : セッション開始。config を含む。
  trial_start     : 試行開始。genome_id・generation を含む。
  env_step        : 環境の 1 ステップ(間引きして記録)。x・energy・fitness_accum。
  network_snapshot: ネットワークの構造スナップショット。可視化用。
  trial_end       : 試行終了。最終 fitness・生死・ステップ数。
  lineage         : 系統樹ノード。genome_id と parent_ids。
  session_end     : セッション終了。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterator


class SnapshotWriter:
    """スレッドセーフな JSONL 書き込みハンドル。"""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(path, "w", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._f.write(line + "\n")
            self._f.flush()

    def close(self) -> None:
        with self._lock:
            self._f.close()

    def __enter__(self) -> "SnapshotWriter":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def iter_records(path: Path) -> Iterator[dict]:
    """JSONL ファイルを 1 行ずつパースして返す。"""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def parse_session(snapshot_path: Path) -> dict:
    """スナップショット JSONL を可視化 API が返す構造化データに変換する。

    返り値:
      - ``session_info`` : session_start レコード。
      - ``trials``       : 試行ごとの env_series・最終 network・結果。
      - ``lineage``      : 系統樹ノードのリスト。
    """
    trials: list[dict] = []
    current: dict | None = None
    lineage: list[dict] = []
    session_info: dict = {}

    for rec in iter_records(snapshot_path):
        t = rec.get("type")

        if t == "session_start":
            session_info = rec

        elif t == "trial_start":
            current = {
                "trial": rec["trial"],
                "genome_id": rec.get("genome_id", ""),
                "generation": rec.get("generation", 0),
                "env_series": [],
                "network": None,
                "steps": 0,
                "fitness": 0.0,
                "alive": False,
            }

        elif t == "env_step" and current is not None:
            current["env_series"].append({
                "step": rec["step"],
                "x": rec.get("x", 0.0),
                "energy": rec.get("energy", 0.0),
                "fitness": rec.get("fitness_accum", 0.0),
            })

        elif t == "network_snapshot" and current is not None:
            # 最後の network_snapshot を上書きして保持(trial_end 直前の状態が残る)。
            current["network"] = {
                "conn_circle": rec.get("conn_circle", 0),
                "nodes": rec.get("nodes", []),
                "edges": rec.get("edges", []),
                "reward_node": rec.get("reward_node"),
            }

        elif t == "trial_end" and current is not None:
            current["steps"] = rec.get("steps", 0)
            current["fitness"] = rec.get("fitness", 0.0)
            current["alive"] = rec.get("alive", False)
            trials.append(current)
            current = None

        elif t == "lineage":
            lineage.append({
                "genome_id": rec["genome_id"],
                "parent_ids": rec.get("parent_ids", []),
                "generation": rec.get("generation", 0),
                "lineage_name": rec.get("lineage_name", "default"),
            })

    return {"session_info": session_info, "trials": trials, "lineage": lineage}
