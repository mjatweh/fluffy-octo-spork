"""Command line: ``python -m life_dashboard {build,serve,schedule,sources}``."""
from __future__ import annotations

import argparse
import functools
import http.server
import logging
import os
import sys
from datetime import date
from pathlib import Path

from .config import PROJECT_DIR, load_config


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); never overrides real env vars."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.removeprefix("export ").strip()
            os.environ.setdefault(key, value.strip().strip("'\""))


def _config(args):
    cfg = load_config(args.config)
    if getattr(args, "dry_run", False) or getattr(args, "sample", False):
        cfg.use_sample_data()
    if getattr(args, "output", None):
        cfg.output_dir = Path(args.output).resolve()
    return cfg


def cmd_build(args) -> int:
    from .pipeline import build

    cfg = _config(args)
    day = date.fromisoformat(args.date) if args.date else None
    result = build(cfg, day=day, offline=args.dry_run)
    if not args.quiet:
        print(result.markdown.read_text(encoding="utf-8"))
    print(f"Dashboard: {result.html}", file=sys.stderr)
    print(f"Briefing:  {result.markdown}", file=sys.stderr)
    if result.vault_note:
        print(f"Vault:     {result.vault_note}", file=sys.stderr)
    print(f"Briefing source: {result.note}", file=sys.stderr)
    failed = [s.name for s in result.data.statuses if not s.ok]
    if failed:
        print(f"Warning: sources failed: {', '.join(failed)}", file=sys.stderr)
    return 0


def cmd_serve(args) -> int:
    cfg = _config(args)
    if args.build or not (cfg.output_dir / "dashboard.html").exists():
        from .pipeline import build

        build(cfg, offline=args.dry_run)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(cfg.output_dir))
    with http.server.ThreadingHTTPServer((args.host, args.port), handler) as httpd:
        print(f"Serving {cfg.output_dir} at http://{args.host}:{args.port}/dashboard.html  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def cmd_schedule(args) -> int:
    from .schedule import snippet

    print(snippet(args.format, args.time, _config(args)))
    return 0


def cmd_sources(args) -> int:
    from .connectors import REGISTRY

    cfg = _config(args)
    print(f"Config: {cfg.source_file or '(none — using bundled sample data)'}")
    for c in cfg.connectors:
        print(f"  enabled: {c.get('name', c['type'])} [{c['type']}]")
    print("Available connector types:", ", ".join(sorted(REGISTRY)))
    return 0


def cmd_auth(args) -> int:
    from .connectors import ConnectorError, build_connector

    cfg = load_config(args.config)
    outlook = [c for c in cfg.connectors if c.get("type") == "outlook"]
    if args.name:
        outlook = [c for c in outlook if c.get("name") == args.name]
    if not outlook:
        print("No enabled [[connectors]] with type = \"outlook\"" + (f" named {args.name!r}" if args.name else "")
              + f" in {cfg.source_file or 'any config file'}.", file=sys.stderr)
        return 1
    for options in outlook:
        conn = build_connector(options, cfg)
        print(f"Signing in to {conn.name}...")
        try:
            path = conn.login()
        except ConnectorError as exc:
            print(f"{conn.name}: sign-in failed: {exc}", file=sys.stderr)
            return 1
        print(f"Signed in. Token saved to {path} (keep it private).")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(PROJECT_DIR / ".env")
    load_dotenv(PROJECT_DIR.parent / ".env")  # shared monorepo .env
    parser = argparse.ArgumentParser(prog="life_dashboard", description="Your day on one page, with a Claude-written morning briefing.")
    parser.add_argument("-c", "--config", help="path to config.toml (default: ./config.toml, $LIFE_DASHBOARD_CONFIG)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="collect data, write briefing and dashboard once")
    b.add_argument("--dry-run", action="store_true", help="offline: sample data + template briefing, no API calls")
    b.add_argument("--sample", action="store_true", help="use bundled sample data (still calls Claude if a key is set)")
    b.add_argument("--date", help="build for YYYY-MM-DD instead of today")
    b.add_argument("--output", help="output directory (default from config: ./output)")
    b.add_argument("-q", "--quiet", action="store_true", help="don't print the briefing")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="serve the output folder over HTTP")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--build", action="store_true", help="rebuild before serving")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--output")
    s.set_defaults(func=cmd_serve)

    sc = sub.add_parser("schedule", help="print a cron / launchd / systemd / GitHub Actions snippet")
    sc.add_argument("--time", default="07:00", help="HH:MM local time (default 07:00)")
    sc.add_argument("--format", choices=["cron", "launchd", "systemd", "github"], default="cron")
    sc.set_defaults(func=cmd_schedule)

    sub.add_parser("sources", help="list configured and available connectors").set_defaults(func=cmd_sources)

    a = sub.add_parser("auth", help="one-time browser sign-in for Outlook / Microsoft 365 email connectors")
    a.add_argument("name", nargs="?", help="connector name (default: every enabled outlook connector)")
    a.set_defaults(func=cmd_auth)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    return args.func(args)
