"""Morning check-in and evening review: question flows, normalization, persistence."""
from __future__ import annotations

import re
from datetime import date as Date
from pathlib import Path
from typing import Callable

from . import prompts, vault
from .llm import LLM
from .store import Store

Ask = Callable[[str], str]
Out = Callable[[str], None]

# Keyword -> root-cause tag. Applied to free text so tags exist even when the user skips them.
TAG_RULES = {
    "meetings": r"meeting|calls?\b|1:1|standup|sync",
    "interruptions": r"interrupt|slack|email|ping|distract|context.switch",
    "low-energy": r"tired|exhaust|sleep|sick|low energy|drained|burn",
    "scope": r"scope|underestimat|took longer|bigger than|rabbit.?hole",
    "dependencies": r"blocked|waiting on|waiting for|depend|approval|review",
    "unclear-priorities": r"unclear|confus|priorit(y|ies) (changed|shifted)|no plan",
    "overcommitment": r"too much|overcommit|too many|overloaded",
    "procrastination": r"procrastinat|avoid|put off|delay",
    "firefighting": r"fire|urgent|incident|outage|escalat",
}


def auto_tags(*texts: str) -> list[str]:
    blob = " ".join(t for t in texts if t).lower()
    return [tag for tag, rx in TAG_RULES.items() if re.search(rx, blob)]


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[;\n]", value)
    return [str(v).strip() for v in value if str(v).strip()]


def _split_csv(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip().lower().replace(" ", "-") for v in (value or []) if str(v).strip()]


def _int(value, lo: int = 0, hi: int = 10) -> int | None:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def parse_status(value) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return 1.0 if value >= 1 else 0.5 if value > 0 else 0.0
    v = str(value).strip().lower()
    if v in {"y", "yes", "done", "true", "1", "x", "complete", "completed"}:
        return 1.0
    if v in {"p", "partial", "half", "~", "0.5", "some"}:
        return 0.5
    return 0.0


def _prompt(ask: Ask, question: str) -> str:
    try:
        return ask(question).strip()
    except EOFError:
        return ""


def _ask_int(ask: Ask, question: str, lo: int = 1, hi: int = 10) -> int | None:
    for _ in range(3):
        raw = _prompt(ask, question)
        if not raw:
            return None
        if (n := _int(raw, lo, hi)) is not None:
            return n
    return None


def today() -> str:
    return Date.today().isoformat()


# --- morning ------------------------------------------------------------------
def morning_context(store: Store, day: str) -> dict:
    prev = store.last_checkin_before(day, "evening")
    prev_date = prev["date"] if prev else None
    # Unfinished priorities from the most recent earlier day that had priorities.
    last_days = [d for d in store.dates(end=day) if d < day and store.get_priorities(d)]
    src = last_days[-1] if last_days else None
    unfinished = [p["text"] for p in store.get_priorities(src) if (p["done"] or 0) < 1] if src else []
    reflection = prev["response"] if prev else ""
    suggestion = ""
    if "Suggestions for tomorrow:" in (reflection or ""):
        tail = reflection.split("Suggestions for tomorrow:", 1)[1].strip().splitlines()
        suggestion = tail[0].lstrip("-* ").strip() if tail else ""
    return {"prev_date": prev_date, "prev_reflection": reflection, "prev_suggestion": suggestion,
            "prev_lessons": (prev["data"].get("lessons") if prev else "") or "",
            "unfinished": unfinished, "unfinished_from": src}


def normalize_morning(raw: dict) -> dict:
    return {
        "priorities": _as_list(raw.get("priorities"))[:5],
        "energy": _int(raw.get("energy"), 1, 10),
        "meetings": _int(raw.get("meetings"), 0, 30),
        "blockers": (raw.get("blockers") or "").strip(),
        "notes": (raw.get("notes") or "").strip(),
    }


def ask_morning(ctx: dict, day: str, ask: Ask = input, out: Out = print) -> dict:
    out(f"Good morning! Check-in for {Date.fromisoformat(day):%A %Y-%m-%d}.")
    if ctx["prev_reflection"]:
        out(f"\nFrom last night's review ({ctx['prev_date']}):\n{ctx['prev_reflection']}\n")
    priorities: list[str] = []
    if ctx["unfinished"]:
        out("Unfinished from " + ctx["unfinished_from"] + ":\n" + prompts._bullets(ctx["unfinished"]))
        if _prompt(ask, "Carry these over? [Y/n] ").lower() not in {"n", "no"}:
            priorities = ctx["unfinished"][:3]
    out("What are your top 3 priorities today? (blank to finish)")
    while len(priorities) < 3:
        p = _prompt(ask, f"  Priority {len(priorities) + 1}: ")
        if not p:
            break
        priorities.append(p)
    return normalize_morning({
        "priorities": priorities,
        "energy": _ask_int(ask, "Energy level right now (1-10)? "),
        "meetings": _ask_int(ask, "How many meetings today? ", 0, 30),
        "blockers": _prompt(ask, "Any blockers or worries? "),
    })


def morning_markdown(answers: dict, brief: str) -> str:
    lines = [f"- [ ] {p}" for p in answers["priorities"]] or ["- (no priorities set)"]
    meta = [f"**Energy:** {answers['energy'] or '?'}/10"]
    if answers.get("meetings") is not None:
        meta.append(f"**Meetings:** {answers['meetings']}")
    out = "**Top priorities**\n" + "\n".join(lines) + "\n\n" + " · ".join(meta)
    if answers.get("blockers"):
        out += f"\n\n**Blockers:** {answers['blockers']}"
    return out + f"\n\n**Assistant:**\n{brief}"


def run_morning(store: Store, llm: LLM, answers: dict, day: str | None = None,
                vault_path: Path | None = None, ctx: dict | None = None) -> dict:
    day = day or today()
    ctx = ctx if ctx is not None else morning_context(store, day)
    answers = normalize_morning(answers)
    brief = llm.generate(prompts.SYSTEM, prompts.morning_prompt(day, answers, ctx),
                         lambda: prompts.dry_morning(day, answers, ctx))
    store.set_priorities(day, answers["priorities"])
    store.save_checkin(day, "morning", answers, brief, energy=answers["energy"],
                       meetings=answers["meetings"])
    note = vault.write_morning(vault_path, day, morning_markdown(answers, brief)) if vault_path else None
    return {"date": day, "answers": answers, "response": brief, "note": note}


# --- evening ------------------------------------------------------------------
def normalize_evening(raw: dict, n_priorities: int) -> dict:
    completed = raw.get("completed", [])
    if isinstance(completed, str):
        completed = [c for c in re.split(r"[,\s]+", completed) if c]
    completed = [parse_status(c) for c in completed][:n_priorities]
    completed += [0.0] * (n_priorities - len(completed))
    didnt = (raw.get("didnt_go_well") or "").strip()
    tags = _split_csv(raw.get("root_causes"))
    tags += [t for t in auto_tags(didnt, raw.get("blockers") or "") if t not in tags]
    return {
        "completed": completed,
        "extra_done": _as_list(raw.get("extra_done")),
        "wins": _as_list(raw.get("wins")),
        "didnt_go_well": didnt,
        "root_causes": tags,
        "energy": _int(raw.get("energy"), 1, 10),
        "mood": _int(raw.get("mood"), 1, 10),
        "meetings": _int(raw.get("meetings"), 0, 30),
        "lessons": (raw.get("lessons") or "").strip(),
    }


def ask_evening(priorities: list[str], day: str, ask: Ask = input, out: Out = print) -> dict:
    out(f"Good evening! Review for {Date.fromisoformat(day):%A %Y-%m-%d}.")
    raw: dict = {}
    if not priorities:
        priorities = _as_list(_prompt(ask, "No priorities were set this morning. What did you "
                                           "plan to do? (separate with ;) ").replace(",", ";"))
        raw["priorities"] = priorities
    raw["completed"] = [_prompt(ask, f"Did you complete '{p}'? [y/n/p(artial)] ") or "n"
                        for p in priorities]
    raw["extra_done"] = _prompt(ask, "Anything else you got done? ")
    raw["wins"] = _prompt(ask, "Wins today? ")
    raw["didnt_go_well"] = _prompt(ask, "What didn't go well, and why? ")
    raw["root_causes"] = _prompt(ask, "Root-cause tags, comma-separated (optional, e.g. "
                                      "meetings, interruptions): ")
    raw["energy"] = _ask_int(ask, "Energy now (1-10)? ")
    raw["mood"] = _ask_int(ask, "Mood / satisfaction with the day (1-10)? ")
    raw["lessons"] = _prompt(ask, "One lesson for tomorrow? ")
    return raw


def evening_markdown(answers: dict, priorities: list[dict], reflection: str) -> str:
    mark = {1.0: "x", 0.5: "/"}
    lines = [f"- [{mark.get(p['done'], ' ')}] {p['text']}" for p in priorities]
    lines += [f"- [x] {e} *(extra)*" for e in answers["extra_done"]]
    out = "**Planned vs done**\n" + ("\n".join(lines) or "- (nothing planned)")
    if answers["wins"]:
        out += "\n\n**Wins**\n" + prompts._bullets(answers["wins"])
    if answers["didnt_go_well"]:
        out += f"\n\n**Didn't go well:** {answers['didnt_go_well']}"
    if answers["root_causes"]:
        out += "\n\n**Root causes:** " + " ".join(f"#{t}" for t in answers["root_causes"])
    out += f"\n\n**Energy:** {answers['energy'] or '?'}/10 · **Mood:** {answers['mood'] or '?'}/10"
    if answers["lessons"]:
        out += f"\n\n**Lesson:** {answers['lessons']}"
    return out + f"\n\n**Reflection:**\n{reflection}"


def run_evening(store: Store, llm: LLM, raw: dict, day: str | None = None,
                vault_path: Path | None = None) -> dict:
    day = day or today()
    if not store.get_priorities(day) and raw.get("priorities"):
        store.set_priorities(day, _as_list(raw["priorities"]))
    priorities = store.get_priorities(day)
    morning = store.get_checkin(day, "morning")
    if morning and raw.get("meetings") is None:
        raw = {**raw, "meetings": morning["meetings"]}
    if morning and morning["data"].get("blockers") and not raw.get("blockers"):
        raw = {**raw, "blockers": morning["data"]["blockers"]}
    answers = normalize_evening(raw, len(priorities))
    for p, done in zip(priorities, answers["completed"]):
        store.mark_priority(day, p["position"], done)
        p["done"] = done
    reflection = llm.generate(prompts.SYSTEM, prompts.evening_prompt(day, answers, priorities),
                              lambda: prompts.dry_evening(day, answers, priorities))
    store.set_tags(day, answers["root_causes"])
    store.save_checkin(day, "evening", answers, reflection, energy=answers["energy"],
                       mood=answers["mood"], meetings=answers["meetings"])
    note = (vault.write_evening(vault_path, day, evening_markdown(answers, priorities, reflection))
            if vault_path else None)
    return {"date": day, "answers": answers, "priorities": priorities,
            "response": reflection, "note": note}
