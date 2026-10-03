"""DryRunLLM: a deterministic, offline stand-in for Claude so the whole flow runs with no API key.

It follows the same protocol as the real model (tool_use blocks -> tool_result -> final text), so
--dry-run exercises the real orchestration code: planning, parallel delegation, a revision round,
worker tool calls (side effects are skipped by the dry-run gate) and the final synthesis.
"""
from __future__ import annotations

import re
from typing import Any

from .llm import LLMResponse, fake_response, text_block, tool_use_block

KEYWORDS = {
    "executive_assistant": "calendar schedule inbox email priorities week meeting time plan standup",
    "researcher": "research market competitor data trend source webinar icp industry",
    "content_marketer": "content post blog newsletter social webinar launch brand marketing",
    "sales_outreach": "outreach sales lead leads prospect icp campaign outbound follow-up pipeline",
    "ops_analyst": "revenue finance metrics kpi review csv cost margin weekly business numbers",
    "knowledge_manager": "notes knowledge vault document sop decisions brain",
    "trading_analyst": "trading trade portfolio stocks stock invest investing holdings market movers insider congress",
}

DELIVERABLES = {
    "Executive Assistant": ["Mon 9-11: deep-work block for the top priority", "Tue/Thu 14-15: outreach + follow-up block",
                            "Fri 16-17: weekly review; inbox triaged to 3 decisions"],
    "Researcher": ["3 audience pain points with evidence to validate", "2 competitor angles to differentiate from",
                   "Open question: confirm budget season for the ICP"],
    "Content Marketer": ["Mon: LinkedIn post - the core problem (hook + story)", "Wed: newsletter - framework + CTA",
                         "Fri: short video/carousel repurposing the newsletter"],
    "Sales & Outreach": ["ICP: owner-led B2B services firms, 5-50 staff", "Sequence: intro email -> day-3 bump -> day-7 value follow-up",
                         "Target: 40 personalized touches, goal 4 booked calls"],
    "Operations & Finance Analyst": ["KPIs to track: leads, booked calls, conversion, revenue/week",
                                     "Baseline from available data; flag missing CSVs", "Recommendation: cap tool spend, reinvest in outreach"],
    "Knowledge Manager": ["Relevant prior notes surfaced for the team", "Decision log entry drafted for this goal",
                          "SOP stub created so the process is repeatable"],
    "Trading Analyst": ["Portfolio: concentration and P/L reviewed against your position limits",
                        "Ideas: each with thesis, signals, size %, entry zone and stop (checked by check_trade_idea)",
                        "Analysis only, not licensed financial advice: you place any trades yourself"],
}


def _agent_name(system: str) -> str:
    return system.split("\n", 1)[0].removeprefix("You are ").split(",")[0].strip()


def _texts(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    out = []
    for b in content or []:
        b = b if isinstance(b, dict) else getattr(b, "model_dump", lambda: {})()
        if b.get("type") == "text":
            out.append(b["text"])
        elif b.get("type") == "tool_result":
            out.append(b["content"] if isinstance(b["content"], str) else str(b["content"]))
    return out


def _short(text: str, n: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "..."


class DryRunLLM:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, *, model: str, system: str, messages: list, tools: list[dict], **_: Any) -> LLMResponse:
        self.calls += 1
        name = _agent_name(system)
        tool_names = {t["name"] for t in tools}
        turn = sum(1 for m in messages if m["role"] == "assistant")
        task = _texts(messages[0]["content"])[0]
        results = [t for m in messages[1:] if m["role"] == "user" for t in _texts(m["content"])]
        if "delegate_task" in tool_names and task.startswith("Goal from the owner"):
            resp = self._chief(system, task, turn, results)
        elif "delegate_task" in tool_names:
            resp = fake_response(text_block(self._synthesis(task, [task, *results], standup="standup" in task.lower())))
        else:
            resp = self._worker(name, task, tool_names, turn, results)
        resp.model = "dry-run"  # priced at $0 in the usage table
        return resp

    # --- chief of staff -----------------------------------------------------------------------
    def _chief(self, system: str, task: str, turn: int, results: list[str]) -> LLMResponse:
        goal = task.split("\n", 1)[1].split("\n\nPlan the work")[0].strip()
        team = re.findall(r"^- (\w+) \(([^)]+)\)", system, re.M)
        if turn == 0:
            words = set(re.findall(r"[a-z\-]+", goal.lower()))
            scored = sorted(team, key=lambda kn: (-len(words & set(KEYWORDS.get(kn[0], "").split())), team.index(kn)))
            picks = scored[:3] if len(scored) >= 3 else scored
            plan = "Plan:\n" + "\n".join(f"{i}. {n}: own the {k.replace('_', ' ')} workstream" for i, (k, n) in enumerate(picks, 1))
            calls = [tool_use_block("delegate_task", {"agent": k, "task": f"For the goal '{goal}', deliver your part as {n}.",
                                                      "context": f"Owner goal: {goal}. Keep it actionable for this week."})
                     for k, n in picks]
            return fake_response(text_block(plan + "\n\nThese are independent, so I'm delegating them in parallel."), *calls)
        if turn == 1 and team and results:
            first = re.search(r"### (.+?) \(", results[0])
            key = next((k for k, n in team if first and n == first.group(1)), team[0][0])
            return fake_response(text_block("Review: solid start, but the first deliverable needs concrete owners and dates."),
                                 tool_use_block("delegate_task", {"agent": key, "task": f"Revise your deliverable for '{goal}': add owners, dates and one success metric.",
                                                                  "context": "Previous draft:\n" + results[0][:1500]}))
        return fake_response(text_block(self._synthesis(goal, results)))

    def _synthesis(self, goal: str, results: list[str], standup: bool = False) -> str:
        sections = re.findall(r"### (.+?)(?: \(.*?\))?\n+(.*?)(?=\n### |\Z)", "\n".join(results), re.S)
        latest: dict[str, str] = {}
        for who, body in sections:  # later entries (revisions) win
            latest[who.strip()] = body.strip()
        if standup:
            first = lambda b: next((l[2:] for l in b.splitlines() if l.startswith("- ")), "no update")
            head = "## Highlights\n" + "\n".join(f"- **{w}**: {_short(first(b), 100)}" for w, b in latest.items())
            plan = "\n".join(f"{i}. {w} - {DELIVERABLES.get(w, ['focus block'])[0]} ({9 + i}:00)" for i, w in enumerate(list(latest)[:5], 1))
            return (f"{head}\n\n## Blockers & decisions for the owner\n- Approve outbound sends queued by Sales & Outreach\n\n"
                    f"## Today's plan\n{plan}\n\n## Delegations queued\n- Follow-ups from the plan above")
        deliverables = "\n\n".join(f"### {w}\n{b}" for w, b in latest.items()) or "_No specialist output._"
        return (f"## Summary\nThe team produced a coordinated plan for: **{_short(goal, 120)}**. "
                f"{len(latest)} specialists contributed; one deliverable went through a revision round.\n\n"
                f"## Deliverables\n{deliverables}\n\n"
                "## Decisions needed from the owner\n- Approve the outreach sequence before anything is sent\n"
                "- Confirm the time blocks on your calendar\n\n"
                "## Next actions\n| Action | Owner | Due |\n|---|---|---|\n"
                "| Review and approve drafts in the workspace | Owner | Today |\n"
                "| Publish first content piece | Content Marketer | Mon |\n"
                "| Send first 20 outreach emails (after approval) | Sales & Outreach | Tue |\n"
                "| Report KPIs in the weekly review | Operations & Finance Analyst | Fri |")

    # --- specialists --------------------------------------------------------------------------
    def _worker(self, name: str, task: str, tools: set[str], turn: int, results: list[str]) -> LLMResponse:
        quoted = re.search(r"'(.+)'[,:]", task.split("<context>")[0])
        topic = _short(quoted.group(1) if quoted else task.split("<context>")[0], 60)
        if turn == 0:
            choice = {
                "Executive Assistant": ("run_sibling", {"project": "exec-assistant", "args": ["morning"]}),
                "Researcher": ("search_knowledge", {"query": topic}),
                "Content Marketer": ("search_knowledge", {"query": "brand voice content ideas"}),
                "Sales & Outreach": ("write_file", {"path": "sales/outreach-draft.md",
                                                    "content": f"# Outreach draft\n\nGoal: {topic}\n\n1. Intro email\n2. Day-3 bump\n3. Day-7 value follow-up\n"}),
                "Operations & Finance Analyst": ("list_files", {}),
                "Knowledge Manager": ("search_knowledge", {"query": topic}),
                "Trading Analyst": ("risk_profile", {}),
            }.get(name)
            if choice and choice[0] in tools:
                return fake_response(text_block(f"Checking {choice[0]} first."), tool_use_block(*choice))
        revised = task.lower().startswith("revise")
        bullets = DELIVERABLES.get(name, ["Deliverable drafted", "Risks noted", "Next step proposed"])
        if revised:
            bullets = [f"{b} - owner: {name}, due: this week" for b in bullets] + ["Success metric: 4 booked calls / week"]
        last = results[-1].strip() if results else ""
        evidence = f"\n\n_Tool check:_ {_short(last, 160) if last not in ('', '[]') else 'nothing relevant found'}" if results else ""
        title = "Revised deliverable" if revised else "Deliverable"
        return fake_response(text_block(f"**{title}** for: {topic}\n\n" + "\n".join(f"- {b}" for b in bullets) + evidence))
