"""Cross-source normalization: sorting, dedupe, conflict detection and
"needs reply" / "overdue" heuristics."""
from __future__ import annotations

import re
from datetime import date

from .models import Email, Event, Task

AUTOMATED_SENDER = re.compile(r"no-?reply|newsletter|notifications?@|mailer-daemon|digest|updates@", re.I)
REPLY_HINT = re.compile(
    r"\?|action required|please (?:reply|confirm|review|send)|can you|could you|would you|let me know|confirm|rsvp",
    re.I,
)


def normalize_events(events: list[Event]) -> list[Event]:
    seen, unique = set(), []
    for ev in events:
        key = (ev.title.strip().lower(), ev.start, ev.all_day)
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    unique.sort(key=lambda e: (not e.all_day, e.start, e.end))
    timed = [e for e in unique if not e.all_day]
    for i, a in enumerate(timed):
        for b in timed[i + 1:]:
            if b.start >= a.end:
                break
            a.conflict = b.conflict = True
    return unique


def needs_reply(mail: Email) -> bool:
    if AUTOMATED_SENDER.search(mail.sender):
        return False
    if mail.flagged:
        return True
    return mail.unread and bool(REPLY_HINT.search(f"{mail.subject} {mail.snippet}"))


def normalize_emails(emails: list[Email], limit: int = 8) -> list[Email]:
    for m in emails:
        m.needs_reply = needs_reply(m)
    emails = sorted(emails, key=lambda m: m.received, reverse=True)
    emails.sort(key=lambda m: (not m.needs_reply, not m.flagged, not m.unread))  # stable
    return emails[:limit]


def normalize_tasks(tasks: list[Task], day: date) -> list[Task]:
    open_tasks = [t for t in tasks if not t.done]
    for t in open_tasks:
        t.overdue = bool(t.due and t.due < day)
        t.due_today = t.due == day
    open_tasks.sort(key=lambda t: (not t.overdue, not t.due_today, t.priority, t.due or date.max, t.title))
    return open_tasks
