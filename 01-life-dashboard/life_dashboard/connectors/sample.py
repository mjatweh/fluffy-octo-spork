"""Bundled sample-data connectors used for --dry-run, demos and tests.

Sample data is stored relative to a fixed anchor day and shifted onto the
requested day, so the demo dashboard always looks like "today".
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from ..config import SAMPLE_DIR
from ..models import Email, Task
from .base import Connector, register
from .ics import events_for_day
from .tasks_file import _priority

SAMPLE_ANCHOR = date(2026, 1, 5)  # the day the sample calendar is written for


@register
class SampleCalendar(Connector):
    type = "sample_calendar"
    kind = "calendar"

    def fetch(self, day: date):
        text = (SAMPLE_DIR / "calendar.ics").read_text(encoding="utf-8")
        shift = day - SAMPLE_ANCHOR
        events = events_for_day(text, SAMPLE_ANCHOR, self.config.tz, source=self.name)
        for ev in events:
            # shift wall-clock time (keeps 09:00 at 09:00 across DST changes)
            ev.start = datetime.combine(ev.start.date() + shift, ev.start.time(), self.config.tz)
            ev.end = datetime.combine(ev.end.date() + shift, ev.end.time(), self.config.tz)
        return events


@register
class SampleEmail(Connector):
    type = "sample_email"
    kind = "email"

    def fetch(self, day: date):
        data = json.loads((SAMPLE_DIR / "emails.json").read_text(encoding="utf-8"))
        morning = datetime.combine(day, datetime.min.time(), self.config.tz) + timedelta(hours=7)
        return [
            Email(
                sender=m["from"],
                subject=m["subject"],
                snippet=m.get("snippet", ""),
                received=morning - timedelta(hours=m.get("hours_ago", 1)),
                unread=m.get("unread", True),
                flagged=m.get("flagged", False),
                source=self.name,
            )
            for m in data
        ]


@register
class SampleTasks(Connector):
    type = "sample_tasks"
    kind = "tasks"

    def fetch(self, day: date):
        data = json.loads((SAMPLE_DIR / "tasks.json").read_text(encoding="utf-8"))
        return [
            Task(
                title=t["title"],
                due=day + timedelta(days=t["due_in_days"]) if "due_in_days" in t else None,
                priority=_priority(t.get("priority", 3)),
                project=t.get("project", ""),
                source=self.name,
            )
            for t in data
        ]
