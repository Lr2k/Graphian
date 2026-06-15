"""セッション制御・系統管理(§5.4)。

ここに置くのは:
  - `SessionConfig`      : 試行の設定(TOML から読まれるデータ型 §9.3)。
  - `LineageRecord` / `PhylogeneticTree` : 系統樹の記録(データ構造であって数学ではないので
                           core に具象実装を置く)。可視化(§9.6)へ渡す。
  - `Session`            : セッション制御の契約(抽象基底)。`run` の本体はダミー環境(§7.1)と
                           ダミー発達ルール(§7.2)が揃ってから実装する ── 本モジュールでは
                           契約と系統データ型までを確定する。

集団モデルは初版では不要(決定2) ── 1 試行は 1 個体 / 1 系統(§9.5)を回す。複数個体や
系統の同時実行は「器」だけ残し、ここでは扱わない。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """1 セッションの設定(§9.3)。TOML 読込・検証は ``persistence/config.py`` が担い、
    本データ型はその結果を保持する。

    フィールド:
      - ``environment``          : 使用する環境モジュール名。
      - ``lineage``              : 系統名(初版は 1 系統 §9.5)。
      - ``trials``               : 試行回数。
      - ``termination``          : 終了条件の識別子(例 "all_sated_or_dead" §7.1)。
      - ``inherit_body_genome``  : 身体 genome をセッションをまたいで継承するか(§7.1 二段構え)。
      - ``env_params``           : 環境の初期値の基準・幅・変動パターン等(§9.3)。
    """

    environment: str
    lineage: str
    trials: int
    termination: str
    inherit_body_genome: bool = True
    env_params: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LineageRecord:
    """系統樹の 1 ノード ── ある genome がどの親から派生したかを追跡する(§5.4)。"""

    genome_id: str
    parent_ids: tuple[str, ...]  # 初版は片親コピーゆえ長さ 1。§8 のブレンドで複数親に。
    generation: int
    lineage: str


class PhylogeneticTree:
    """系統樹。genome の親子関係を保持し、可視化(系統樹 §9.6)へ渡す。

    数学ではなくデータ構造なので core に具象実装を置く。
    """

    __slots__ = ("_records",)

    def __init__(self) -> None:
        self._records: dict[str, LineageRecord] = {}

    def add(self, record: LineageRecord) -> None:
        self._records[record.genome_id] = record

    def get(self, genome_id: str) -> LineageRecord:
        return self._records[genome_id]

    def children(self, genome_id: str) -> tuple[LineageRecord, ...]:
        return tuple(r for r in self._records.values() if genome_id in r.parent_ids)

    def roots(self) -> tuple[LineageRecord, ...]:
        return tuple(r for r in self._records.values() if not r.parent_ids)

    def __len__(self) -> int:
        return len(self._records)

    def to_records(self) -> list[dict]:
        """JSONL 永続化用(§9.4)。"""
        return [
            {
                "genome_id": r.genome_id,
                "parent_ids": list(r.parent_ids),
                "generation": r.generation,
                "lineage": r.lineage,
            }
            for r in self._records.values()
        ]

    @classmethod
    def from_records(cls, records: list[dict]) -> "PhylogeneticTree":
        tree = cls()
        for d in records:
            tree.add(
                LineageRecord(
                    genome_id=str(d["genome_id"]),
                    parent_ids=tuple(str(p) for p in d["parent_ids"]),
                    generation=int(d["generation"]),
                    lineage=str(d["lineage"]),
                )
            )
        return tree


class Session(ABC):
    """セッション制御の契約(§5.4)。

    具象オーケストレータは、設定に基づき試行を立ち上げ(環境-身体プロセスと情報処理系
    プロセスを起動)、生死判定を受け取り、適応度と genome を回収し、淘汰・配合・継承を
    回し、保存・再開を担う。`run` の本体実装はダミー環境/発達ルールが揃う次段階で行う。
    """

    @abstractmethod
    def run(self, config: SessionConfig) -> None:
        """設定に基づき試行を実行する(§5.4)。"""

    @abstractmethod
    def save(self, path: str) -> None:
        """セッションを中断・保存する(JSONL スナップショット §9.4)。"""

    @classmethod
    @abstractmethod
    def resume(cls, path: str) -> "Session":
        """保存済みセッションを再開する(§5.4)。"""
