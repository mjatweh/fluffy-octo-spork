import csv
import io
from datetime import date

from content_agent import calendar_plan as cp


def test_week_slots_follow_cadence_and_rotate_pillars(brand):
    slots = cp.make_slots(brand, date(2026, 10, 5), 7)  # Monday
    assert len(slots) == 3 + 5 + 3 + 2 + 1  # linkedin, x, instagram, tiktok, newsletter
    assert [x["slot"] for x in slots] == list(range(1, len(slots) + 1))
    pillars = [p.name for p in brand.pillars]
    assert [x["pillar"] for x in slots[:4]] == pillars
    assert {x["channel"] for x in slots if x["weekday"] == "Thu"} >= {"newsletter"}


def test_month_has_four_weeks(brand):
    assert len(cp.make_slots(brand, date(2026, 10, 5), 28)) == 56


def test_dry_run_calendar_csv(brand):
    entries = cp.build_calendar(brand, start=date(2026, 10, 5), dry_run=True)
    rows = list(csv.DictReader(io.StringIO(cp.to_csv(entries))))
    assert list(rows[0]) == cp.FIELDS
    assert len(rows) == 14 and all(r["topic"] and r["hook"] and r["status"] == "planned" for r in rows)
    assert rows[0]["date"] == "2026-10-05" and rows[0]["weekday"] == "Mon"
    md = cp.to_markdown(entries, brand)
    assert "| Date | Channel |" in md and "Northbeam AI" in md


def test_llm_calendar_fills_slots_and_flags_gaps(brand, fake):
    slots = cp.make_slots(brand, date(2026, 10, 5), 7, channels=["linkedin"])
    ideas = [{"slot": 1, "topic": "T1", "hook": "H1", "cta": "C1"}, {"slot": 2, "topic": "T2", "hook": "H2", "cta": "C2"}]
    client, llm = fake({"ideas": ideas})
    entries = cp.build_calendar(brand, llm, start=date(2026, 10, 5), channels=["linkedin"])
    assert len(entries) == len(slots) == 3
    assert entries[0].topic == "T1" and entries[2].status == "needs idea"
    assert "1. 2026-10-05 | linkedin" in client.requests[0]["messages"][0]["content"]


def test_next_monday():
    assert cp.next_monday(date(2026, 10, 3)) == date(2026, 10, 5)
    assert cp.next_monday(date(2026, 10, 5)) == date(2026, 10, 12)
