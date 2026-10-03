"""python -m second_brain <command> ..."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from . import agent_api, config


def _vault_parent() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--vault", help="vault folder (default $SECOND_BRAIN_VAULT, $VAULT_PATH or ./vault)")
    return p


def build_parser() -> argparse.ArgumentParser:
    vp = _vault_parent()
    ap = argparse.ArgumentParser(prog="second_brain", description="Obsidian second brain for business & life admin.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a vault from vault_template/")
    s.add_argument("dest", nargs="?", help="destination (default: the --vault path)")
    s.add_argument("--vault")
    s.add_argument("--force", action="store_true", help="merge into a non-empty folder")

    s = sub.add_parser("ingest", parents=[vp], help="file everything in a drop folder into the vault")
    s.add_argument("inbox", nargs="?", help="drop folder (default: <vault>/00 Inbox)")
    s.add_argument("--dry-run", "--offline", dest="dry_run", action="store_true",
                   help="no Claude calls: deterministic offline heuristics")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--move", dest="move", action="store_true", default=None, help="delete originals after ingest")
    g.add_argument("--keep", dest="move", action="store_false", help="keep originals in the drop folder")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("index", parents=[vp], help="(re)build the local search index")
    s.add_argument("--force", action="store_true", help="rebuild from scratch")

    s = sub.add_parser("search", parents=[vp], help="BM25 search over notes")
    s.add_argument("query", nargs="+")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("ask", parents=[vp], help="answer a question from your notes, with citations")
    s.add_argument("question", nargs="+")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--dry-run", "--offline", dest="dry_run", action="store_true")

    s = sub.add_parser("reminders", parents=[vp], help="upcoming renewals/expiries/deadlines")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--overdue", action="store_true", help="include past-due dates")
    s.add_argument("--today", help="pretend today is YYYY-MM-DD")
    s.add_argument("--json", action="store_true")

    sub.add_parser("mcp", parents=[vp], help="run the MCP server (stdio)")
    sub.add_parser("tools", help="print Claude tool definitions as JSON")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    vault = config.vault_path(getattr(args, "vault", None))

    if args.cmd == "init":
        from .vault import init_vault

        dest = config.vault_path(args.dest or args.vault)
        init_vault(dest, force=args.force)
        print(f"Vault created at {dest}\nOpen it in Obsidian: 'Open folder as vault' -> {dest}")
        return 0
    if args.cmd == "tools":
        print(json.dumps(agent_api.TOOLS, indent=2))
        return 0
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main

        return mcp_main(vault)
    if not vault.is_dir():
        print(f"Vault not found: {vault}. Run `python -m second_brain init --vault {vault}` first.", file=sys.stderr)
        return 2

    if args.cmd == "ingest":
        from .ingest import ingest

        inbox = config.vault_path(args.inbox) if args.inbox else vault / "00 Inbox"
        results = ingest(inbox, vault, dry_run=args.dry_run, move=args.move,
                         log=(lambda m: None) if args.json else print)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            counts = {s: sum(r["status"] == s for r in results) for s in ("ingested", "skipped", "error")}
            print(f"Done: {counts['ingested']} ingested, {counts['skipped']} skipped, {counts['error']} errors.")
        return 1 if any(r["status"] == "error" for r in results) else 0
    if args.cmd == "index":
        from .index import refresh

        print(f"Indexed {len(refresh(vault, force=args.force)['docs'])} notes.")
        return 0
    if args.cmd == "search":
        hits = agent_api.search(" ".join(args.query), args.k, vault=vault)
        if args.json:
            print(json.dumps(hits, indent=2))
        else:
            for h in hits:
                print(f"{h['score']:7.3f}  {h['path']}\n         {h['snippet']}")
            if not hits:
                print("No matches.")
        return 0
    if args.cmd == "ask":
        from .qa import ask

        print(ask(vault, " ".join(args.question), k=args.k, dry_run=args.dry_run))
        return 0
    if args.cmd == "reminders":
        from .reminders import format_table

        today = dt.date.fromisoformat(args.today) if args.today else None
        rows = agent_api.upcoming_dates(args.days, args.overdue, vault=vault, today=today)
        print(json.dumps(rows, indent=2) if args.json else format_table(rows))
        return 0
    return 1
