"""Generate a deterministic week of sample check-ins (for demos and end-to-end tests)."""
from __future__ import annotations

from datetime import date as Date, timedelta
from pathlib import Path

from .checkins import run_evening, run_morning
from .llm import LLM
from .store import Store

# (priorities, energy_am, meetings, blockers, completed, energy_pm, mood, wins, didnt_go_well, lessons)
WEEK = [
    (["Draft Q4 strategy memo", "Review hiring pipeline", "Prep board update"], 8, 2, "",
     "y,y,p", 7, 8, "Memo first draft done before lunch", "Board prep slipped - started it too late",
     "Start the hardest thing first"),
    (["Finish board update", "1:1s with directs", "Clear inbox to zero"], 6, 5, "Waiting on finance numbers",
     "p,y,n", 4, 5, "Great 1:1 with Sam", "Back-to-back meetings all afternoon, no focus time; waiting on finance",
     "Protect a focus block on heavy meeting days"),
    (["Finish board update", "Vendor contract review", "Write team update"], 5, 6, "",
     "n,p,y", 3, 4, "Team update well received", "Too many meetings and constant Slack interruptions",
     "Say no to optional meetings"),
    (["Finish board update", "Customer escalation call", "Plan offsite agenda"], 7, 2, "",
     "y,y,p", 7, 7, "Board update shipped; escalation resolved", "Offsite planning took longer than expected",
     "Timebox planning work"),
    (["Offsite agenda final", "Quarterly OKR scoring", "Mentor session"], 8, 1, "",
     "y,y,y", 8, 9, "Perfect focus day - all three done", "", "Light meeting days are gold"),
    (["Read strategy docs", "Weekly planning"], 6, 0, "", "y,n", 6, 7, "Caught up on reading",
     "Got distracted by email and skipped planning", "Plan before opening email"),
    (["Family time", "Prep Monday priorities"], 7, 0, "", "y,y", 8, 8, "Rested and prepped", "", ""),
]


def seed_week(store: Store, end: Date, vault_path: Path | None = None, llm: LLM | None = None) -> list[str]:
    llm = llm or LLM(dry_run=True)
    start = end - timedelta(days=len(WEEK) - 1)
    days = []
    for i, (pri, e_am, mtg, blk, done, e_pm, mood, wins, bad, lesson) in enumerate(WEEK):
        day = (start + timedelta(days=i)).isoformat()
        run_morning(store, llm, {"priorities": pri, "energy": e_am, "meetings": mtg, "blockers": blk},
                    day, vault_path)
        run_evening(store, llm, {"completed": done, "energy": e_pm, "mood": mood, "wins": wins,
                                 "didnt_go_well": bad, "lessons": lesson}, day, vault_path)
        days.append(day)
    return days
