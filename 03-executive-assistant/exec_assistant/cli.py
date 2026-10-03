"""Command-line interface: python -m exec_assistant <command> ..."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import date as Date, timedelta
from pathlib import Path

from . import checkins, notify
from .config import Config, load_dotenv
from .demo import seed_week
from .llm import LLM
from .store import Store
from .weekly import compute_stats, render_stats_md, run_weekly, week_range

DAYS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


def _load_answers(path: str | None) -> dict:
    if not path:
        return {}
    text = sys.stdin.read() if path == "-" else Path(path).read_text()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("--answers must contain a JSON object")
    return data


def _merge(base: dict, **flags) -> dict:
    return {**base, **{k: v for k, v in flags.items() if v not in (None, [], "")}}


def _ctx(args) -> tuple[Config, Store, LLM, Path | None]:
    cfg = Config.from_env()
    if args.model:
        cfg.model = args.model
    store = Store(cfg.db_path)
    llm = LLM(model=cfg.model, dry_run=args.dry_run)
    return cfg, store, llm, None if args.no_vault else cfg.vault_path


def cmd_morning(args) -> int:
    cfg, store, llm, vault = _ctx(args)
    raw = _load_answers(args.answers)
    day = args.date or raw.pop("date", None) or checkins.today()
    raw = _merge(raw, priorities=args.priority, energy=args.energy, meetings=args.meetings,
                 blockers=args.blockers)
    ctx = checkins.morning_context(store, day)
    if not raw:
        raw = checkins.ask_morning(ctx, day)
    res = checkins.run_morning(store, llm, raw, day, vault, ctx=ctx)
    print(f"\n=== Morning brief {day} ===\n{res['response']}")
    if res["note"]:
        print(f"\n(saved to {res['note']})")
    return 0


def cmd_evening(args) -> int:
    cfg, store, llm, vault = _ctx(args)
    raw = _load_answers(args.answers)
    day = args.date or raw.pop("date", None) or checkins.today()
    raw = _merge(raw, completed=args.done, energy=args.energy, mood=args.mood, wins=args.wins,
                 didnt_go_well=args.went_wrong, root_causes=args.tags, lessons=args.lessons,
                 priorities=args.planned)
    if not raw:
        raw = checkins.ask_evening([p["text"] for p in store.get_priorities(day)], day)
    res = checkins.run_evening(store, llm, raw, day, vault)
    print(f"\n=== Evening reflection {day} ===\n{res['response']}")
    if res["note"]:
        print(f"\n(saved to {res['note']})")
    return 0


def cmd_weekly(args) -> int:
    cfg, store, llm, vault = _ctx(args)
    end = Date.fromisoformat(args.end) if args.end else Date.today()
    res = run_weekly(store, llm, end, out_dir=cfg.reports_dir,
                     out_path=Path(args.out) if args.out else None, vault_path=vault)
    print(res["markdown"])
    print(f"\n(saved to {res['path']}" + (f" and {res['note']}" if res["note"] else "") + ")",
          file=sys.stderr)
    if args.notify:
        notify.send(f"Weekly review {res['stats']['week']}", res["markdown"],
                    cfg.webhook_url, use_desktop=not args.no_desktop)
    return 0


def cmd_history(args) -> int:
    cfg = Config.from_env()
    store = Store(cfg.db_path)
    start = (Date.today() - timedelta(days=args.days - 1)).isoformat()
    days = store.days(start, "9999-12-31")
    if args.json:
        print(json.dumps(days, indent=2, default=str))
        return 0
    if not days:
        print("No check-ins yet. Try: python -m exec_assistant morning  (or seed-demo)")
    mark = {1.0: "x", 0.5: "/", 0.0: " "}
    for d in days:
        mo, ev = d["morning"], d["evening"]
        head = f"{d['date']} {Date.fromisoformat(d['date']):%a}"
        info = [f"energy {mo['energy']}" if mo and mo["energy"] else "",
                f"→{ev['energy']}" if ev and ev["energy"] else "",
                f" mood {ev['mood']}" if ev and ev["mood"] else ""]
        print(f"\n{head}  [{'M' if mo else '-'}{'E' if ev else '-'}]  {''.join(info).strip()}")
        for p in d["priorities"]:
            print(f"  [{mark.get(p['done'], '?') if ev else ' '}] {p['text']}")
        if d["tags"]:
            print("  root causes: " + ", ".join(d["tags"]))
        if ev and ev["data"].get("wins"):
            print("  wins: " + "; ".join(ev["data"]["wins"]))
    return 0


def cmd_stats(args) -> int:
    cfg = Config.from_env()
    store = Store(cfg.db_path)
    end = Date.fromisoformat(args.end) if args.end else Date.today()
    start, end = week_range(end, args.days)
    stats = compute_stats(store.days(start.isoformat(), end.isoformat()), start, end)
    print(json.dumps(stats, indent=2) if args.json else render_stats_md(stats))
    return 0


def _hm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


def cmd_schedule(args) -> int:
    root = Path(__file__).resolve().parent.parent
    py = shlex.quote(sys.executable)
    prefix = f"cd {shlex.quote(str(root))} && {py} -m exec_assistant"
    data_dir = Config.from_env().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)  # cron's log redirect needs it to exist
    log = f">> {shlex.quote(str(data_dir / 'cron.log'))} 2>&1"
    mh, mm = _hm(args.morning)
    eh, em = _hm(args.evening)
    wday, wtime = args.weekly.split()
    wh, wm = _hm(wtime)
    dow = DAYS[wday[:3].lower()]
    print("# Executive Assistant schedule - add with `crontab -e`.")
    print("# Cron has a minimal env: set VAULT_PATH / EA_WEBHOOK_URL / ANTHROPIC_API_KEY here or in .env")
    print("# For desktop notifications from cron on Linux you may also need DISPLAY / DBUS_SESSION_BUS_ADDRESS.")
    print(f"{mm} {mh} * * * {prefix} nudge morning {log}")
    print(f"{em} {eh} * * * {prefix} nudge evening {log}")
    print(f"{wm} {wh} * * {dow} {prefix} weekly --notify {log}")
    print("\n# Alternative: only nudge for the weekly review instead of auto-sending it:")
    print(f"# {wm} {wh} * * {dow} {prefix} nudge weekly {log}")
    return 0


def cmd_nudge(args) -> int:
    cfg = Config.from_env()
    title, msg = notify.NUDGES[args.kind]
    sent = notify.send(title, msg, cfg.webhook_url, use_desktop=not args.no_desktop)
    print(f"(sent via: {', '.join(sent)})", file=sys.stderr)
    return 0


def cmd_seed_demo(args) -> int:
    cfg, store, llm, vault = _ctx(args)
    end = Date.fromisoformat(args.end) if args.end else Date.today()
    days = seed_week(store, end, vault, LLM(dry_run=True))
    print(f"Seeded {len(days)} days ({days[0]} → {days[-1]}) into {cfg.db_path}")
    print(f"Next: python -m exec_assistant weekly --dry-run --end {days[-1]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", help="offline templated responses, no API calls")
    common.add_argument("--no-vault", action="store_true", help="don't write to the Obsidian vault")
    common.add_argument("--model", help="override CLAUDE_MODEL")

    p = argparse.ArgumentParser(prog="exec_assistant", description="Daily check-in executive assistant.")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("morning", parents=[common], help="morning check-in")
    m.add_argument("--date", help="YYYY-MM-DD (default today)")
    m.add_argument("--answers", help="JSON answers file ('-' for stdin) for non-interactive runs")
    m.add_argument("--priority", action="append", help="repeat up to 3 times")
    m.add_argument("--energy", type=int)
    m.add_argument("--meetings", type=int)
    m.add_argument("--blockers")
    m.set_defaults(func=cmd_morning)

    e = sub.add_parser("evening", parents=[common], help="evening review")
    e.add_argument("--date")
    e.add_argument("--answers")
    e.add_argument("--done", help="status per priority, e.g. 'y,n,p'")
    e.add_argument("--planned", help="priorities if none were set in the morning ('a; b; c')")
    e.add_argument("--energy", type=int)
    e.add_argument("--mood", type=int)
    e.add_argument("--wins")
    e.add_argument("--went-wrong")
    e.add_argument("--tags", help="root-cause tags, comma-separated")
    e.add_argument("--lessons")
    e.set_defaults(func=cmd_evening)

    w = sub.add_parser("weekly", parents=[common], help="weekly rollup of the last 7 days")
    w.add_argument("--end", help="last day of the 7-day window (default today)")
    w.add_argument("--out", help="also write markdown to this path")
    w.add_argument("--notify", action="store_true", help="send the report via EA_WEBHOOK_URL/desktop")
    w.add_argument("--no-desktop", action="store_true")
    w.set_defaults(func=cmd_weekly)

    h = sub.add_parser("history", help="show past entries")
    h.add_argument("--days", type=int, default=14)
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=cmd_history)

    s = sub.add_parser("stats", help="computed stats for a window")
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--end")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_stats)

    sc = sub.add_parser("schedule", help="print cron lines")
    sc.add_argument("--morning", default="08:00")
    sc.add_argument("--evening", default="21:00")
    sc.add_argument("--weekly", default="Sun 18:00")
    sc.set_defaults(func=cmd_schedule)

    n = sub.add_parser("nudge", help="send a check-in reminder (for cron)")
    n.add_argument("kind", choices=sorted(notify.NUDGES))
    n.add_argument("--no-desktop", action="store_true")
    n.set_defaults(func=cmd_nudge)

    d = sub.add_parser("seed-demo", parents=[common], help="generate a week of sample data")
    d.add_argument("--end", help="last day of the demo week (default today)")
    d.set_defaults(func=cmd_seed_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # shared monorepo .env
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled - nothing saved.")
        return 130
