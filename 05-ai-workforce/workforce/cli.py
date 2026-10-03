"""Command line: python -m workforce run|ask|standup|roster|history|playbooks"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .playbooks import list_playbooks, render_playbook
from .runs import list_runs, new_run_dir, save_run
from .safety import Approver
from .team import Team


def _echo(event: dict) -> None:
    kind, who = event["type"], event["agent"]
    msg = {
        "delegate": lambda: f"-> {who} delegates to {event['to']}" + (f" (revision {event['revision']})" if event.get("revision") else "")
                            + f": {event['task'][:90]}",
        "tool_call": lambda: f"   {who} uses {event['tool']}",
        "side_effect_skipped": lambda: f"   {who}: {event['tool']} skipped (dry-run)",
        "approval_denied": lambda: f"   {who}: {event['tool']} denied by human",
        "max_turns": lambda: f"   {who} hit max turns",
    }.get(kind)
    if msg:
        print(msg(), file=sys.stderr, flush=True)


def _make_llm(args, config):
    if args.dry_run:
        from .dryrun import DryRunLLM
        return DryRunLLM()
    from .llm import AnthropicLLM
    return AnthropicLLM(use_fallbacks=bool(config.settings.get("refusal_fallbacks", True)))


def _execute(args, config, title: str, call) -> int:
    run_dir = new_run_dir(config.runs_dir, title)
    team = Team(config, _make_llm(args, config), approver=Approver(auto_yes=args.yes), dry_run=args.dry_run,
                transcript_path=run_dir / "transcript.jsonl", echo=None if args.quiet else _echo)
    try:
        result = call(team)
    except Exception as e:
        if type(e).__module__.startswith("anthropic"):
            print(f"Claude API error: {e}\nTip: set ANTHROPIC_API_KEY (or `ant auth login`), or use --dry-run.",
                  file=sys.stderr)
            return 2
        raise
    report = save_run(run_dir, result, team)
    print(report.read_text(encoding="utf-8") if not args.quiet else "")
    print(f"\nReport: {report}\nTranscript: {run_dir / 'transcript.jsonl'}", file=sys.stderr)
    return 0


def cmd_run(args, config) -> int:
    if args.playbook:
        overrides = dict(v.split("=", 1) for v in args.var)
        title, goal = render_playbook(config.playbooks_dir, args.playbook, overrides)
        if args.goal:
            goal += f"\n\nAdditional instructions: {args.goal}"
    elif args.goal:
        title = goal = args.goal
    else:
        print("give a goal or --playbook NAME", file=sys.stderr)
        return 2
    return _execute(args, config, title, lambda team: team.run(goal))


def cmd_ask(args, config) -> int:
    agent = config.find_agent(args.agent)
    return _execute(args, config, f"ask-{agent.key}-{args.task}", lambda team: team.ask(agent.key, args.task))


def cmd_standup(args, config) -> int:
    return _execute(args, config, "standup", lambda team: team.standup(args.focus or ""))


def cmd_roster(args, config) -> int:
    from .tools import build_registry
    team_tools = build_registry()
    print(f"Lead: {config.agents[config.lead].name}\n")
    for key, a in config.agents.items():
        star = "*" if key == config.lead else " "
        print(f"{star} {key:<20} {a.name}  [{a.model}{', effort=' + a.effort if a.effort else ''}, max_turns={a.max_turns}]")
        print(f"    {a.role}")
        tools = [t + (" (approval)" if t in team_tools and team_tools.get(t).side_effect else "") for t in a.tools]
        print(f"    tools: {', '.join(tools + [s + ' (server)' for s in a.server_tools])}\n")
    print("Sibling CLIs (run_sibling allowlist):")
    for k, s in config.siblings.items():
        installed = "installed" if (config.root / s["dir"]).is_dir() else "not found"
        print(f"  {k:<16} python -m {s['module']} {{{'|'.join(s['commands'])}}}  ({installed})")
    return 0


def cmd_history(args, config) -> int:
    runs = list_runs(config.runs_dir, args.limit)
    if not runs:
        print(f"No runs yet in {config.runs_dir}")
    for r in runs:
        mode = "dry" if r.get("dry_run") else "live"
        cost = r.get("usage", {}).get("cost_usd", 0)
        print(f"{r['created']}  {r['kind']:<8} {mode:<4} ${cost:<8.4f} {r['goal'].splitlines()[0][:70]}\n    {r['dir']}")
    return 0


def cmd_playbooks(args, config) -> int:
    for name, b in list_playbooks(config.playbooks_dir).items():
        print(f"{name:<24} {b.get('title', '')} - {b.get('description', '')}")
        if b.get("vars"):
            print(f"{'':<24} vars: {', '.join(f'{k}={v!r}' for k, v in b['vars'].items())}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="workforce", description="AI Workforce: a team of Claude agents led by a Chief of Staff.")
    p.add_argument("--roster", type=Path, help="path to roster.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--dry-run", action="store_true", help="offline scripted LLM; no API calls, no side effects")
        sp.add_argument("--yes", "-y", action="store_true", help="auto-approve side-effect tools")
        sp.add_argument("--quiet", "-q", action="store_true", help="no progress output")

    r = sub.add_parser("run", help="Chief of Staff orchestrates the team toward a goal")
    r.add_argument("goal", nargs="?", default="")
    r.add_argument("--playbook", help="playbook name from playbooks/")
    r.add_argument("--var", action="append", default=[], metavar="KEY=VALUE", help="playbook variable")
    common(r)
    r.set_defaults(fn=cmd_run)

    a = sub.add_parser("ask", help="talk to one agent directly")
    a.add_argument("agent")
    a.add_argument("task")
    common(a)
    a.set_defaults(fn=cmd_ask)

    s = sub.add_parser("standup", help="daily standup: status from every agent + today's plan")
    s.add_argument("--focus", default="")
    common(s)
    s.set_defaults(fn=cmd_standup)

    sub.add_parser("roster", help="list agents and tools").set_defaults(fn=cmd_roster)
    h = sub.add_parser("history", help="list past runs")
    h.add_argument("--limit", type=int, default=20)
    h.set_defaults(fn=cmd_history)
    sub.add_parser("playbooks", help="list playbooks").set_defaults(fn=cmd_playbooks)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.roster)
    try:
        return args.fn(args, config)
    except KeyError as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 2
