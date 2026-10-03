"""Content calendar: code lays out dated slots across channels & pillars; Claude (or dry-run) fills ideas."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta

from . import dryrun, prompts, schemas as s
from .brand import Brand
from .llm import LLM

# Posting weekdays per channel (Mon=0).
CADENCE = {"linkedin": (0, 2, 4), "x": (0, 1, 2, 3, 4), "x-thread": (2,), "instagram": (1, 3, 5),
           "tiktok": (1, 4), "newsletter": (3,), "blog-outline": (0,)}
DEFAULT_CHANNELS = ("linkedin", "x", "instagram", "tiktok", "newsletter")
FIELDS = ["date", "weekday", "channel", "pillar", "topic", "hook", "cta", "status"]


@dataclass
class Entry:
    date: str
    weekday: str
    channel: str
    pillar: str
    topic: str = ""
    hook: str = ""
    cta: str = ""
    status: str = "planned"


def next_monday(today: date | None = None) -> date:
    today = today or date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def make_slots(brand: Brand, start: date, days: int, channels=DEFAULT_CHANNELS) -> list[dict]:
    pillars = [p.name for p in brand.pillars] or ["General"]
    slots = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for ch in channels:
            if day.weekday() in CADENCE.get(prompts.get_type(ch).key, ()):
                slots.append({"slot": len(slots) + 1, "date": day.isoformat(), "weekday": day.strftime("%a"),
                              "channel": prompts.get_type(ch).key, "pillar": pillars[len(slots) % len(pillars)]})
    return slots


def build_calendar(brand: Brand, llm: LLM | None = None, *, start: date | None = None, period: str = "week",
                   days: int | None = None, channels=DEFAULT_CHANNELS, dry_run: bool = False) -> list[Entry]:
    start = start or next_monday()
    days = days or {"week": 7, "month": 28}[period]
    slots = make_slots(brand, start, days, channels)
    if dry_run:
        plan = dryrun.calendar_ideas(brand, slots)
    else:
        llm = llm or LLM()
        data = llm.generate_json(prompts.SYSTEM, brand.context(),
                                 [{"role": "user", "content": prompts.calendar_prompt(slots)}],
                                 s.schema_for(s.CalendarPlan))
        plan = s.from_dict(s.CalendarPlan, data)
    ideas = {i.slot: i for i in plan.ideas}
    entries = []
    for sl in slots:
        idea = ideas.get(sl["slot"])
        entries.append(Entry(sl["date"], sl["weekday"], sl["channel"], sl["pillar"],
                             *((idea.topic, idea.hook, idea.cta) if idea else ("", "", "")),
                             status="planned" if idea else "needs idea"))
    return entries


def to_csv(entries: list[Entry]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    for e in entries:
        w.writerow(e.__dict__)
    return buf.getvalue()


def to_markdown(entries: list[Entry], brand: Brand) -> str:
    esc = lambda t: t.replace("|", "\\|")  # noqa: E731
    lines = [f"# Content calendar — {brand.name}", "",
             f"{entries[0].date} → {entries[-1].date} · {len(entries)} pieces" if entries else "No slots.", ""]
    week = None
    for e in entries:
        wk = date.fromisoformat(e.date).isocalendar()[1]
        if wk != week:
            week = wk
            lines += ["", f"## Week {wk}", "", "| Date | Channel | Pillar | Topic | Hook | CTA |", "|---|---|---|---|---|---|"]
        lines.append(f"| {e.weekday} {e.date} | {e.channel} | {esc(e.pillar)} | {esc(e.topic)} | {esc(e.hook)} | {esc(e.cta)} |")
    lines += ["", "Draft any slot with: `python -m content_agent generate <channel> --topic \"<topic>\" --pillar \"<pillar>\"`", ""]
    return "\n".join(lines)
