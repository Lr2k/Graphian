"""CLI ── 全機能を叩けるコマンドラインインターフェース(§9.9)。

サブコマンド:
  init      : デフォルト設定ファイルを生成する。
  validate  : 設定ファイルを検証する。
  run       : セッションを実行する。
  resume    : 保存済みセッションを再開する(後続フェーズで完全実装)。
  viz       : 保存済みスナップショットを可視化する Web UI を起動する。

使用例:
  graphian init --output config.toml
  graphian validate config.toml
  graphian run config.toml
  graphian viz --session-dir ./sessions --port 8765
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# サブコマンド実装
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    from graphian.persistence.config import write_default_config

    out = Path(args.output)
    if out.exists() and not args.force:
        print(f"エラー: {out} は既に存在します。上書きするには --force を指定してください。")
        return 1
    write_default_config(out)
    print(f"設定ファイルを生成しました: {out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from graphian.persistence.config import load_config

    path = Path(args.config)
    if not path.exists():
        print(f"エラー: {path} が見つかりません。")
        return 1
    try:
        load_config(path)
        print(f"OK: {path} は有効な設定ファイルです。")
        return 0
    except ValueError as exc:
        print(exc)
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    from graphian.orchestrator import SimpleSession
    from graphian.persistence.config import load_config

    path = Path(args.config)
    if not path.exists():
        print(f"エラー: {path} が見つかりません。")
        return 1
    try:
        config = load_config(path)
    except ValueError as exc:
        print(exc)
        return 1

    session_dir = Path(
        args.session_dir or config.get("output", {}).get("session_dir", "./sessions")
    )

    session = SimpleSession()
    try:
        sdir = session.run_from_config(config, session_dir)
        print(f"セッション完了。出力: {sdir}")
        return 0
    except Exception as exc:
        print(f"セッション実行中にエラーが発生しました: {exc}")
        raise


def cmd_resume(args: argparse.Namespace) -> int:
    # §11: resume は後続フェーズで完全実装。初版はスタブ。
    print(
        "resume は後続フェーズで実装予定です(§11)。\n"
        f"保存データを確認する場合は 'graphian viz --session-dir {args.session_dir}' を使用してください。"
    )
    return 0


def cmd_viz(args: argparse.Namespace) -> int:
    from graphian.viz.server import start_server

    session_dir = Path(args.session_dir)
    port = int(args.port)
    if not session_dir.exists():
        print(f"警告: {session_dir} が存在しません。セッションを先に実行してください。")
        session_dir.mkdir(parents=True, exist_ok=True)
    start_server(session_dir, port=port, open_browser=not args.no_browser)
    return 0


# ---------------------------------------------------------------------------
# パーサ定義
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graphian",
        description="身体と環境への応答を通じてネットワークを発達させる存在を作る(Graphian 初版)",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # init
    p_init = sub.add_parser("init", help="デフォルト設定ファイルを生成する")
    p_init.add_argument("--output", "-o", default="config.toml", help="出力先 (default: config.toml)")
    p_init.add_argument("--force", "-f", action="store_true", help="既存ファイルを上書きする")

    # validate
    p_val = sub.add_parser("validate", help="設定ファイルを検証する")
    p_val.add_argument("config", help="設定ファイルのパス")

    # run
    p_run = sub.add_parser("run", help="セッションを実行する")
    p_run.add_argument("config", help="設定ファイルのパス")
    p_run.add_argument(
        "--session-dir", default=None,
        help="セッション保存先(指定しなければ config の [output].session_dir を使用)",
    )

    # resume
    p_res = sub.add_parser("resume", help="保存済みセッションを再開する(後続フェーズで完全実装)")
    p_res.add_argument(
        "--session-dir", default="./sessions",
        help="セッション保存先 (default: ./sessions)",
    )

    # viz
    p_viz = sub.add_parser("viz", help="保存済みスナップショットを可視化する Web UI を起動する")
    p_viz.add_argument(
        "--session-dir", default="./sessions",
        help="セッション保存先 (default: ./sessions)",
    )
    p_viz.add_argument("--port", default="8765", help="ポート番号 (default: 8765)")
    p_viz.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")

    return parser


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

_COMMANDS = {
    "init": cmd_init,
    "validate": cmd_validate,
    "run": cmd_run,
    "resume": cmd_resume,
    "viz": cmd_viz,
}


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    fn = _COMMANDS[args.command]
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
