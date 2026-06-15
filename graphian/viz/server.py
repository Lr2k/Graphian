"""保存済みスナップショットを可視化する Web サーバ(§9.6 / §9.9)。

標準ライブラリ `http.server` のみで実装する(外部依存なし)。
静的ファイルを `graphian/ui/web/` から配信し、データ API を `/api/*` で提供する。

API エンドポイント:
  GET /api/sessions           → session ディレクトリの一覧(JSON)
  GET /api/session?dir=<name> → session の解析済みデータ(JSON)
  GET /api/events?dir=<name>  → events.jsonl の内容(JSON 配列)
  GET / または /*.html|*.js   → 静的ファイル
"""

from __future__ import annotations

import functools
import http.server
import json
import logging
import urllib.parse
from pathlib import Path

from graphian.persistence.snapshot import parse_session

log = logging.getLogger(__name__)

# 静的ファイルのディレクトリ(このファイルから相対)。
_WEB_DIR = Path(__file__).parent.parent / "ui" / "web"


class _GraphianHandler(http.server.SimpleHTTPRequestHandler):
    """静的ファイル配信 + データ API を兼ねるハンドラ。"""

    # SimpleHTTPRequestHandler.__init__ に directory を渡すのを通じて
    # 静的ファイルのルートを設定する。
    def __init__(self, *args, session_dir: Path, **kwargs):
        self._session_dir = session_dir
        super().__init__(*args, directory=str(_WEB_DIR), **kwargs)

    # ------------------------------------------------------------------
    # ルーティング
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/sessions":
            self._api_sessions()
        elif path == "/api/session":
            params = urllib.parse.parse_qs(parsed.query)
            self._api_session(params.get("dir", [None])[0])
        elif path == "/api/events":
            params = urllib.parse.parse_qs(parsed.query)
            self._api_events(params.get("dir", [None])[0])
        else:
            # index.html へのフォールバック(SPA 的に使う)
            if path == "/":
                self.path = "/index.html"
            super().do_GET()

    def log_message(self, fmt: str, *args) -> None:
        log.debug("HTTP %s", fmt % args)

    # ------------------------------------------------------------------
    # API ハンドラ
    # ------------------------------------------------------------------

    def _api_sessions(self) -> None:
        sessions = []
        if self._session_dir.is_dir():
            for d in sorted(self._session_dir.iterdir(), reverse=True):
                if d.is_dir() and (d / "snapshot.jsonl").exists():
                    sessions.append({"name": d.name})
        self._json(sessions)

    def _api_session(self, dir_name: str | None) -> None:
        if not dir_name:
            self._error(400, "dir パラメータが必要です")
            return
        snap = self._session_dir / dir_name / "snapshot.jsonl"
        if not snap.exists():
            self._error(404, f"セッションが見つかりません: {dir_name}")
            return
        try:
            data = parse_session(snap)
        except Exception as exc:
            self._error(500, str(exc))
            return
        self._json(data)

    def _api_events(self, dir_name: str | None) -> None:
        if not dir_name:
            self._error(400, "dir パラメータが必要です")
            return
        events_path = self._session_dir / dir_name / "events.jsonl"
        if not events_path.exists():
            self._json([])
            return
        records = []
        try:
            with open(events_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception as exc:
            self._error(500, str(exc))
            return
        self._json(records)

    # ------------------------------------------------------------------
    # レスポンスヘルパ
    # ------------------------------------------------------------------

    def _json(self, data) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code: int, msg: str) -> None:
        body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_server(session_dir: Path, port: int = 8765, *, open_browser: bool = True) -> None:
    """Web UI サーバを起動する(ブロッキング)。"""
    handler = functools.partial(_GraphianHandler, session_dir=session_dir)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Graphian Web UI を起動しました: {url}")
    print("Ctrl+C で停止します。")
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバを停止しました。")
    finally:
        server.server_close()
