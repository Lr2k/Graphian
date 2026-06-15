"""TOML 設定ファイルの読込・検証・デフォルト生成(§9.3)。

設定の検証は性能より**明快なエラーメッセージ**を優先する(§9.3)。
「どの項目がなぜ不正か」を人間に伝えることを第一義とする。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

# ---------------------------------------------------------------------------
# デフォルト設定テンプレート(graphian init で生成)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = """\
[session]
environment = "phototaxis_1d"
trials = 5
termination = "all_sated_or_dead"
inherit_body_genome = true
max_steps_per_trial = 1000
# クロック比: A が clock_a_steps 進むたびに B が clock_b_steps 回更新される。
# 1:1 より大きな比を設定すると A が相対的に高頻度になる(§2.2: 比率非固定)。
clock_a_steps = 2
clock_b_steps = 1

# [lineage.<名前>] で系統を定義する。初版は 1 系統(§9.5)。
[lineage.default]
slots_per_circle = [4, 8]
circle_diameters = [0.5, 1.0]
reward_circle = 0
reward_slot = 0
seed = 42
move_speed = 0.2

[environment]
x_light = 0.5

[output]
session_dir = "./sessions"
log_level = "INFO"
"""


def load_config(path: str | Path) -> dict:
    """TOML を読込み、検証済みの辞書を返す。

    不正な項目が 1 つでもあれば、すべての問題をまとめた ValueError を送出する。
    """
    path = Path(path)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    _validate(data, path)
    return data


def write_default_config(path: str | Path) -> None:
    """デフォルト設定ファイルを書き出す(graphian init)。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(DEFAULT_CONFIG, encoding="utf-8")


# ---------------------------------------------------------------------------
# 検証(内部)
# ---------------------------------------------------------------------------


def _validate(data: dict, path: Path) -> None:
    errors: list[str] = []

    session = data.get("session", {})
    if "environment" not in session:
        errors.append("[session].environment が必要です")
    trials = session.get("trials")
    if trials is None:
        errors.append("[session].trials が必要です")
    elif not isinstance(trials, int) or trials < 1:
        errors.append(f"[session].trials は 1 以上の整数である必要があります: {trials!r}")
    max_steps = session.get("max_steps_per_trial", 1000)
    if not isinstance(max_steps, int) or max_steps < 1:
        errors.append(f"[session].max_steps_per_trial は 1 以上の整数: {max_steps!r}")

    lineage = data.get("lineage", {})
    if not lineage:
        errors.append("[lineage.<名前>] セクションが 1 つ以上必要です(§9.3)")
    for name, lconf in lineage.items():
        prefix = f"[lineage.{name}]"
        for key in ("slots_per_circle", "circle_diameters", "seed"):
            if key not in lconf:
                errors.append(f"{prefix}.{key} が必要です")
        slots = lconf.get("slots_per_circle", [])
        diams = lconf.get("circle_diameters", [])
        if slots and diams and len(slots) != len(diams):
            errors.append(
                f"{prefix}: slots_per_circle({len(slots)}) と "
                f"circle_diameters({len(diams)}) の長さが一致していません"
            )
        if slots and any(s < 1 for s in slots):
            errors.append(f"{prefix}.slots_per_circle の各要素は 1 以上")
        if diams and any(not (0 < d <= 1.0) for d in diams):
            errors.append(f"{prefix}.circle_diameters の各要素は (0, 1]")
        rc = lconf.get("reward_circle", 0)
        rs = lconf.get("reward_slot", 0)
        if slots and not (0 <= rc < len(slots)):
            errors.append(f"{prefix}.reward_circle={rc} が円数({len(slots)})の範囲外")
        if slots and 0 <= rc < len(slots) and not (0 <= rs < slots[rc]):
            errors.append(
                f"{prefix}.reward_slot={rs} が 円{rc} のスロット数({slots[rc]})の範囲外"
            )

    output = data.get("output", {})
    log_level = output.get("log_level", "INFO")
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        errors.append(f"[output].log_level が不正: {log_level!r}")

    if errors:
        lines = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(f"{path} の設定に問題があります:\n{lines}")
