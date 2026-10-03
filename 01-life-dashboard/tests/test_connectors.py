import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from life_dashboard.config import SAMPLE_DIR, Config
from life_dashboard.connectors import REGISTRY, ConnectorError, build_connector
from life_dashboard.connectors.ics import events_for_day
from life_dashboard.connectors.imap import parse_message
from life_dashboard.connectors.tasks_file import parse_json, parse_markdown
from life_dashboard.connectors.todoist import parse_tasks

NY = ZoneInfo("America/New_York")


def test_registry_has_builtins():
    assert {"ics", "imap", "tasks_file", "todoist", "sample_calendar", "sample_email", "sample_tasks"} <= set(REGISTRY)


def test_unknown_connector_type(config):
    with pytest.raises(ConnectorError):
        build_connector({"type": "nope"}, config)


def test_sample_calendar_is_shifted_to_requested_day(config, day):
    events = build_connector({"type": "sample_calendar"}, config).fetch(day)
    titles = [e.title for e in events]
    assert "Q1 roadmap review" in titles and "Team stand-up" in titles
    assert "Cancelled sync" not in titles and "Dentist (tomorrow)" not in titles
    roadmap = next(e for e in events if e.title == "Q1 roadmap review")
    assert roadmap.start == datetime(2026, 10, 5, 10, 0, tzinfo=NY)
    assert "Decide on the two launch candidates" in roadmap.description
    assert any(e.all_day for e in events)


def test_sample_email_and_tasks(config, day):
    emails = build_connector({"type": "sample_email"}, config).fetch(day)
    tasks = build_connector({"type": "sample_tasks"}, config).fetch(day)
    assert len(emails) == len(json.loads((SAMPLE_DIR / "emails.json").read_text()))
    assert all(e.received.date() <= day for e in emails)
    assert any(t.due == day for t in tasks)
    assert next(t for t in tasks if t.title.startswith("Finish")).priority == 1


ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:a
DTSTART;TZID=Europe/London:20261005T140000
DTEND;TZID=Europe/London:20261005T150000
SUMMARY:London call\\, important
END:VEVENT
BEGIN:VEVENT
UID:b
DTSTART:20261005T120000Z
DURATION:PT30M
SUMMARY:UTC sync
END:VEVENT
BEGIN:VEVENT
UID:weekly
DTSTART:20260907T080000
DTEND:20260907T083000
RRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL=20261231T000000Z
SUMMARY:Biweekly
END:VEVENT
BEGIN:VEVENT
UID:daily
DTSTART:20261001T070000
DTEND:20261001T071500
RRULE:FREQ=DAILY;COUNT=3
SUMMARY:Three-day habit
END:VEVENT
BEGIN:VEVENT
UID:ex
DTSTART:20261001T180000
DTEND:20261001T190000
RRULE:FREQ=DAILY
EXDATE:20261005T180000
SUMMARY:Excluded today
END:VEVENT
BEGIN:VEVENT
UID:moved
DTSTART:20261001T090000
DTEND:20261001T093000
RRULE:FREQ=DAILY
SUMMARY:Daily check
END:VEVENT
BEGIN:VEVENT
UID:moved
RECURRENCE-ID:20261005T090000
DTSTART:20261005T110000
DTEND:20261005T113000
SUMMARY:Daily check (moved)
END:VEVENT
BEGIN:VEVENT
UID:trip
DTSTART;VALUE=DATE:20261004
DTEND;VALUE=DATE:20261007
SUMMARY:Conference trip
END:VEVENT
END:VCALENDAR
"""


def test_ics_parser_handles_common_features(day):
    events = {e.title: e for e in events_for_day(ICS, day, NY)}
    assert events["London call, important"].start == datetime(2026, 10, 5, 9, 0, tzinfo=NY)
    assert events["UTC sync"].start.hour == 8 and events["UTC sync"].duration_minutes == 30
    assert "Biweekly" in events  # 2026-09-07 + 4 weeks
    assert "Three-day habit" not in events  # COUNT exhausted
    assert "Excluded today" not in events
    assert "Daily check" not in events and events["Daily check (moved)"].start.hour == 11
    assert events["Conference trip"].all_day  # multi-day event overlapping today
    assert "Biweekly" not in {e.title for e in events_for_day(ICS, date(2026, 9, 28), NY)}


def test_ics_connector_reads_file(tmp_path, config, day):
    (tmp_path / "cal.ics").write_text(ICS)
    config.base_dir = tmp_path
    events = build_connector({"type": "ics", "source": "cal.ics", "name": "Work"}, config).fetch(day)
    assert events and all(e.source == "Work" for e in events)


def test_ics_connector_missing_source(config, day):
    with pytest.raises(ConnectorError):
        build_connector({"type": "ics"}, config).fetch(day)


def test_markdown_tasks():
    tasks = parse_markdown((SAMPLE_DIR / "tasks.md").read_text(), "todo.md")
    by_title = {t.title: t for t in tasks}
    assert by_title["Book flights for offsite"].due == date(2026, 10, 3)
    assert by_title["Book flights for offsite"].priority == 2
    assert by_title["Book flights for offsite"].project == "travel"
    assert by_title["Renew passport"].due == date(2026, 10, 10) and by_title["Renew passport"].priority == 2
    assert by_title["Reply to landlord"].priority == 1
    assert by_title["Pay rent"].done
    assert by_title["Water the plants"].due is None
    assert len(tasks) == 5


def test_tasks_file_connector_skips_done(tmp_path, config, day):
    config.base_dir = SAMPLE_DIR
    tasks = build_connector({"type": "tasks_file", "path": "tasks.md"}, config).fetch(day)
    assert "Pay rent" not in [t.title for t in tasks]


def test_json_tasks():
    tasks = parse_json('{"tasks": [{"title": "A", "due": "2026-10-05", "priority": "urgent"}, {"title": "B", "priority": 9}]}')
    assert tasks[0].priority == 1 and tasks[0].due == date(2026, 10, 5) and tasks[1].priority == 4


def test_todoist_parsing():
    payload = {"results": [{"content": "Pay bill", "priority": 4, "due": {"date": "2026-10-05"}}, {"content": "Someday", "priority": 1}]}
    tasks = parse_tasks(payload)
    assert tasks[0].priority == 1 and tasks[0].due == date(2026, 10, 5)
    assert tasks[1].due is None and tasks[1].priority == 3
    assert parse_tasks([{"content": "legacy list shape"}])[0].title == "legacy list shape"


def test_todoist_requires_token(config, day, monkeypatch):
    monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
    with pytest.raises(ConnectorError, match="TODOIST_API_TOKEN"):
        build_connector({"type": "todoist", "token_env": "TODOIST_API_TOKEN"}, config).fetch(day)


def test_imap_message_parsing():
    raw = (
        b"From: =?utf-8?q?Jos=C3=A9?= <jose@example.com>\r\n"
        b"Subject: Quick question\r\nDate: Mon, 05 Oct 2026 08:00:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\nCan you   send the deck?\r\n"
    )
    mail = parse_message(raw, b"\\Flagged", "IMAP", NY)
    assert mail.sender == "José <jose@example.com>"
    assert mail.subject == "Quick question" and mail.snippet == "Can you send the deck?"
    assert mail.unread and mail.flagged and mail.received.hour == 4
