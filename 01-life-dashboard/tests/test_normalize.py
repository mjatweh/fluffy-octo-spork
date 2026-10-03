from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from life_dashboard.models import Email, Event, Task
from life_dashboard.normalize import needs_reply, normalize_emails, normalize_events, normalize_tasks

NY = ZoneInfo("America/New_York")


def at(h, m=0):
    return datetime(2026, 10, 5, h, m, tzinfo=NY)


def test_events_sorted_deduped_and_conflicts():
    evs = [
        Event("B", at(13, 15), at(14)),
        Event("A", at(13), at(13, 30)),
        Event("A", at(13), at(13, 30)),  # duplicate from a second calendar
        Event("C", at(14), at(15)),  # touches B but doesn't overlap
        Event("Holiday", at(0), at(0) + timedelta(days=1), all_day=True),
    ]
    out = normalize_events(evs)
    assert [e.title for e in out] == ["Holiday", "A", "B", "C"]
    assert [e.conflict for e in out] == [False, True, True, False]


def test_needs_reply_heuristics():
    now = at(7)
    assert needs_reply(Email("Ann <ann@x.com>", "Can you review?", now))
    assert needs_reply(Email("Ann <ann@x.com>", "FYI", now, flagged=True, unread=False))
    assert not needs_reply(Email("GitHub <noreply@github.com>", "Can you review #4?", now))
    assert not needs_reply(Email("Ann <ann@x.com>", "Weekly notes", now))


def test_emails_prioritized_and_limited():
    now = at(7)
    mails = [Email(f"P{i} <p{i}@x.com>", "hello", now - timedelta(hours=i)) for i in range(5)]
    mails.append(Email("Boss <b@x.com>", "Please confirm the budget", now - timedelta(hours=9)))
    out = normalize_emails(mails, limit=3)
    assert len(out) == 3 and out[0].sender.startswith("Boss") and out[1].sender.startswith("P0")


def test_tasks_flags_and_order():
    day = date(2026, 10, 5)
    tasks = [
        Task("later", due=day + timedelta(days=3), priority=1),
        Task("today low", due=day, priority=4),
        Task("overdue", due=day - timedelta(days=1), priority=3),
        Task("done", due=day, done=True),
        Task("no date", priority=2),
    ]
    out = normalize_tasks(tasks, day)
    assert [t.title for t in out] == ["overdue", "today low", "later", "no date"]
    assert out[0].overdue and out[1].due_today and not out[2].overdue
