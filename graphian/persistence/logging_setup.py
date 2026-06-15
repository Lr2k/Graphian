"""ログ設定(§9.11)。

2 種類のログを設定する:
  - **システムログ**: 標準ライブラリ `logging`。コンソール(stderr)とファイルに出力。
  - **事象ログ**: 環境内で何が起きたかを JSONL で記録。人間と LLM の両方が読める形式。

`setup_logging` はセッション開始時に 1 回呼ぶ。以後は `get_event_logger()` で
どこからでも事象ログを書ける。
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

_event_logger: "EventLogger | None" = None


def setup_logging(session_dir: Path, log_level: str = "INFO") -> "EventLogger":
    """システムログと事象ログを設定してEventLoggerを返す。"""
    global _event_logger

    session_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger("graphian")
    root.setLevel(level)
    if not root.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(level)
        ch.setFormatter(fmt)
        root.addHandler(ch)
        fh = logging.FileHandler(session_dir / "system.log", encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    _event_logger = EventLogger(session_dir / "events.jsonl")
    return _event_logger


def get_event_logger() -> "EventLogger":
    """現在の EventLogger を返す。setup_logging 前は null ロガーになる。"""
    global _event_logger
    if _event_logger is None:
        _event_logger = EventLogger(None)
    return _event_logger


class EventLogger:
    """事象ログ(JSONL)への書き込みハンドル(§9.11)。

    各レコードは ``{"event": "<type>", "timestamp": "...", ...}`` の形式をとり、
    人間と LLM の両方が読める(§9.11)。
    """

    def __init__(self, path: Path | None) -> None:
        self._lock = threading.Lock()
        self._f = open(path, "w", encoding="utf-8") if path else None

    def log(self, event_type: str, **kwargs) -> None:
        record = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            if self._f:
                self._f.write(line + "\n")
                self._f.flush()
        logging.getLogger("graphian.events").info(line)

    def close(self) -> None:
        with self._lock:
            if self._f:
                self._f.close()
                self._f = None
