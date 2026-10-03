"""Run directories, markdown reports, history and the optional Second Brain export."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

from .team import Team, TeamResult


def slugify(text: str, n: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].strip("-") or "run"


def new_run_dir(runs_dir: Path, title: str) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = runs_dir / f"{stamp}-{slugify(title)}"
    i = 1
    while d.exists():
        i += 1
        d = runs_dir / f"{stamp}-{slugify(title)}-{i}"
    d.mkdir(parents=True)
    return d


def render_report(result: TeamResult, team: Team) -> str:
    t = team.usage.total
    head = [
        f"# {result.kind.title()}: {result.goal.splitlines()[0][:120]}",
        "",
        f"- **Date:** {dt.datetime.now():%Y-%m-%d %H:%M}",
        f"- **Mode:** {'dry-run (scripted LLM, no side effects)' if team.dry_run else 'live'}",
        f"- **Duration:** {result.seconds:.1f}s - **Requests:** {t['requests']} - **Est. cost:** ${t['cost_usd']:.4f}",
        f"- **Knowledge backend:** {team.brain.backend}",
        "",
    ]
    if result.kind == "run" and "\n" in result.goal:
        head += ["## Goal", "", result.goal, ""]
    body = [result.output.strip(), ""]
    tail = []
    if result.delegations:
        tail += ["## Delegation log", "", "| # | Agent | Task | Rev | Turns | Secs |", "|---:|---|---|---:|---:|---:|"]
        for i, d in enumerate(result.delegations, 1):
            task = d["task"].replace("|", "/").replace("\n", " ")[:90]
            tail.append(f"| {i} | {d['agent']} | {task} | {d['revision']} | {d['turns']} | {d['seconds']} |")
        tail.append("")
    tail += ["## Usage", "", team.usage.table(), "", "_Transcript: `transcript.jsonl`_", ""]
    return "\n".join(head + body + tail)


def save_run(run_dir: Path, result: TeamResult, team: Team) -> Path:
    report = render_report(result, team)
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    meta = {"kind": result.kind, "goal": result.goal, "created": dt.datetime.now().isoformat(timespec="seconds"),
            "dry_run": team.dry_run, "seconds": round(result.seconds, 2), "stop_reason": result.stop_reason,
            "usage": team.usage.total, "agents": sorted({d["agent"] for d in result.delegations})}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    export_to_vault(report, result, team)
    return run_dir / "report.md"


def export_to_vault(report: str, result: TeamResult, team: Team) -> Path | None:
    """If VAULT_PATH is set, file the report at <vault>/Agents/YYYY-MM-DD-<slug>.md (skipped in dry-run)."""
    vault = os.environ.get("VAULT_PATH")
    if not vault or team.dry_run:
        return None
    path = Path(vault) / "Agents" / f"{dt.date.today():%Y-%m-%d}-{slugify(result.goal)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = f"---\ntype: agent-run\nkind: {result.kind}\ndate: {dt.date.today()}\ntags: [ai-workforce]\n---\n\n"
    path.write_text(front + report, encoding="utf-8")
    team.transcript.log("system", "vault_export", path=str(path))
    return path


def list_runs(runs_dir: Path, limit: int = 20) -> list[dict]:
    out = []
    for meta in sorted(runs_dir.glob("*/meta.json"), reverse=True)[:limit]:
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        m["dir"] = str(meta.parent)
        out.append(m)
    return out
