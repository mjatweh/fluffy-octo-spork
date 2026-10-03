"""Prompt builders for Claude plus deterministic templates used in dry-run/offline mode."""
from __future__ import annotations

import json

SYSTEM = (
    "You are a sharp, warm executive assistant who runs a daily check-in practice with "
    "your principal: a morning check-in, an evening review and a weekly rollup. You are "
    "concise and concrete, you notice patterns, and you never pad. Write in plain "
    "markdown with no top-level headings (the caller adds them). Address the user as 'you'."
)

# Advice keyed by root-cause tag; used by dry-run templates.
TAG_ADVICE = {
    "meetings": "Block a 90-minute no-meeting focus window before your first meeting.",
    "interruptions": "Batch Slack/email into two fixed windows and go do-not-disturb otherwise.",
    "low-energy": "Protect sleep tonight and put the hardest task in your peak-energy hours.",
    "scope": "Cut tomorrow's top priority to the smallest shippable slice and define 'done' up front.",
    "dependencies": "Send unblock requests first thing in the morning, with a clear ask and deadline.",
    "unclear-priorities": "Write the single outcome that would make tomorrow a win before opening email.",
    "overcommitment": "Plan only two priorities tomorrow and leave buffer for the unexpected.",
    "procrastination": "Start the dreaded task with a 15-minute timer before anything else.",
    "firefighting": "Reserve an hour for reactive work so fires don't eat your priorities.",
}
DEFAULT_ADVICE = "Pick one priority that matters most tomorrow and do it first."


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items) or "- (none)"


# --- morning ----------------------------------------------------------------
def morning_prompt(day: str, answers: dict, ctx: dict) -> str:
    return (
        f"Morning check-in for {day}.\n\n"
        f"Last evening review ({ctx.get('prev_date') or 'none'}):\n{ctx.get('prev_reflection') or '(none)'}\n\n"
        f"Unfinished priorities carried from then:\n{_bullets(ctx.get('unfinished', []))}\n\n"
        f"Today's answers:\n{json.dumps(answers, indent=2)}\n\n"
        "Write a short morning brief (under 120 words): confirm the single most important "
        "priority, flag any risk from energy level, meeting load or blockers, and give one "
        "tactical tip for the day. Reference yesterday's lessons if relevant."
    )


def dry_morning(day: str, answers: dict, ctx: dict) -> str:
    pri = answers.get("priorities") or []
    energy = answers.get("energy")
    lines = [f"**Most important today:** {pri[0] if pri else 'decide your #1 priority before 9am'}."]
    if energy is not None:
        tip = ("energy is low - do the hardest thing early and keep the list short"
               if energy <= 4 else "good energy - protect it for deep work on priority #1"
               if energy >= 7 else "steady energy - pace yourself with short breaks")
        lines.append(f"- Energy {energy}/10: {tip}.")
    if (answers.get("meetings") or 0) >= 4:
        lines.append(f"- {answers['meetings']} meetings today: meeting-heavy days tend to eat "
                     "priorities, so finish one before your first meeting.")
    if answers.get("blockers"):
        lines.append(f"- Blocker: {answers['blockers']} - send the unblock request first thing.")
    if ctx.get("unfinished"):
        lines.append(f"- Carried over: {', '.join(ctx['unfinished'])}.")
    if ctx.get("prev_suggestion"):
        lines.append(f"- From last night: {ctx['prev_suggestion']}")
    return "\n".join(lines)


# --- evening ----------------------------------------------------------------
def evening_prompt(day: str, answers: dict, priorities: list[dict]) -> str:
    plan = "\n".join(f"- [{_status(p['done'])}] {p['text']}" for p in priorities) or "(no priorities set)"
    return (
        f"Evening review for {day}.\n\nPlanned priorities and outcome:\n{plan}\n\n"
        f"Review answers:\n{json.dumps(answers, indent=2)}\n\n"
        "Write a short reflection (2-4 sentences) on what went well and what didn't and why, "
        "then a line 'Suggestions for tomorrow:' followed by 1-2 concrete bullet suggestions."
    )


def _status(done) -> str:
    return {1.0: "x", 0.5: "~"}.get(done, " ")


def dry_evening(day: str, answers: dict, priorities: list[dict]) -> str:
    total = len(priorities)
    done = sum(p["done"] or 0 for p in priorities)
    tags = answers.get("root_causes") or []
    parts = [f"You completed {done:g} of {total} planned priorities today."
             if total else "You didn't set priorities this morning."]
    if answers.get("wins"):
        parts.append(f"Biggest win: {answers['wins'][0]}.")
    if answers.get("didnt_go_well"):
        parts.append(f"What got in the way: {answers['didnt_go_well']}"
                     + (f" (root causes: {', '.join(tags)})." if tags else "."))
    if answers.get("lessons"):
        parts.append(f"Lesson: {answers['lessons']}")
    advice = [TAG_ADVICE[t] for t in tags if t in TAG_ADVICE][:2] or [DEFAULT_ADVICE]
    unfinished = [p["text"] for p in priorities if (p["done"] or 0) < 1]
    if unfinished and len(advice) < 2:
        advice.append(f"Decide first thing whether '{unfinished[0]}' carries over or gets dropped.")
    return " ".join(parts) + "\n\nSuggestions for tomorrow:\n" + _bullets(advice)


# --- weekly -----------------------------------------------------------------
def weekly_prompt(stats: dict, days_compact: list[dict]) -> str:
    return (
        f"Weekly rollup for {stats['week']} ({stats['start']} to {stats['end']}).\n\n"
        f"Computed stats (authoritative, do not recompute):\n{json.dumps(stats, indent=2)}\n\n"
        f"Daily entries:\n{json.dumps(days_compact, indent=2)}\n\n"
        "Write the weekly analysis in markdown with exactly these sections as '###' headings:\n"
        "### Summary (3-4 sentences, cite numbers)\n"
        "### Keep / Stop / Start (bullets prefixed **Keep:**, **Stop:**, **Start:**; 1-2 each)\n"
        "### 3 Concrete Improvements (numbered, each specific and testable next week)\n"
        "### Proposed Focus for the New Week (one theme sentence + top 3 outcomes)\n"
        "Ground every point in the data: recurring root causes, energy trend, patterns."
    )


def dry_weekly(stats: dict) -> str:
    rate = stats["completion_rate"]
    causes = [c for c, _ in stats["root_causes"]]
    top = causes[0] if causes else None
    rate_txt = f"{rate:.0%}" if rate is not None else "n/a"
    summary = (f"You logged {stats['days_logged']} of 7 days and completed "
               f"{stats['completed']:g} of {stats['planned_reviewed']} reviewed priorities ({rate_txt}). "
               f"Energy averaged {stats['avg_energy'] or 'n/a'}/10 and was {stats['energy_trend']}.")
    if top:
        summary += f" The most frequent root cause was '{top}' ({stats['root_causes'][0][1]} days)."
    best = stats.get("best_day")
    best_wins = [w["text"] for w in stats["wins"] if best and w["date"] == best["date"]]
    keep = (f"**Keep:** what worked on {best['weekday']} ({best['rate']:.0%} completion)"
            + (f" - {best_wins[0]}." if best_wins else ".")) if best else \
        "**Keep:** the daily check-in habit."
    stop = f"**Stop:** letting '{top}' derail priorities." if top else \
        "**Stop:** planning more than you can finish."
    start = "**Start:** " + (TAG_ADVICE.get(causes[1], DEFAULT_ADVICE) if len(causes) > 1
                             else "a 10-minute Friday plan for the next week.")
    improvements = [TAG_ADVICE.get(c, DEFAULT_ADVICE) for c in causes[:3]]
    if stats.get("carried_over"):
        improvements.append(f"Finish or explicitly drop '{stats['carried_over'][0]}' by Tuesday.")
    for filler in ("Cap daily priorities at three and rank them.",
                   "Do a 2-minute midday check on priority #1.",
                   "Do both check-ins every day so next week's rollup is complete."):
        if len(improvements) >= 3:
            break
        improvements.append(filler)
    theme = (f"Protect focus time against '{top}'" if top else "Consistent execution on fewer priorities")
    outcomes = (stats.get("carried_over") or [])[:2] + ["Hit 80%+ priority completion"]
    return "\n".join([
        "### Summary", summary, "",
        "### Keep / Stop / Start", f"- {keep}", f"- {stop}", f"- {start}", "",
        "### 3 Concrete Improvements",
        *[f"{i}. {s}" for i, s in enumerate(improvements[:3], 1)], "",
        "### Proposed Focus for the New Week", f"**Theme:** {theme}.",
        *[f"- {o}" for o in outcomes[:3]],
    ])
