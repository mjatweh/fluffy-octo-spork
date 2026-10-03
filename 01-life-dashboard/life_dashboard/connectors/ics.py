"""iCalendar (.ics) connector: local file, http(s) or webcal URL.

Works with the "secret iCal address" Google Calendar, Outlook and iCloud all
expose, so no OAuth is needed. A small stdlib parser handles the common subset:
timed / all-day / multi-day events, TZID, UTC, RRULE (DAILY/WEEKLY/MONTHLY/
YEARLY with INTERVAL, BYDAY, UNTIL, COUNT), EXDATE, RECURRENCE-ID overrides
and cancelled events.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

from ..models import Event
from .base import Connector, register

WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _split(line: str) -> tuple[str, dict[str, str], str]:
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    pdict = {}
    for p in params:
        k, _, v = p.partition("=")
        pdict[k.upper()] = v.strip('"')
    return name.upper(), pdict, value


def _zone(tzid: str | None, default: tzinfo) -> tzinfo:
    if not tzid:
        return default
    try:
        return ZoneInfo(tzid)
    except Exception:  # unknown / Windows zone names
        return default


def parse_dt(value: str, params: dict[str, str], tz: tzinfo) -> tuple[datetime, bool]:
    """Return (aware datetime in ``tz``, all_day)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
        d = datetime.strptime(value[:8], "%Y%m%d").date()
        return datetime.combine(d, time(), tz), True
    if value.endswith("Z"):
        dt = datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo("UTC"))
    else:
        dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=_zone(params.get("TZID"), tz))
    return dt.astimezone(tz), False


def parse_events(text: str, tz: tzinfo) -> list[dict[str, Any]]:
    """Parse VEVENT blocks into raw dicts (dates already converted to ``tz``)."""
    events, cur = [], None
    for line in _unfold(text):
        name, params, value = _split(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            cur = {"exdates": set()}
        elif name == "END" and value.upper() == "VEVENT" and cur is not None:
            if "start" in cur:
                events.append(cur)
            cur = None
        elif cur is None:
            continue
        elif name in ("DTSTART", "DTEND"):
            dt, all_day = parse_dt(value, params, tz)
            cur["start" if name == "DTSTART" else "end"] = dt
            if name == "DTSTART":
                cur["all_day"] = all_day
        elif name == "DURATION":
            cur["duration"] = _parse_duration(value)
        elif name == "RRULE":
            cur["rrule"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
        elif name == "EXDATE":
            for v in value.split(","):
                cur["exdates"].add(parse_dt(v, params, tz)[0].date())
        elif name == "RECURRENCE-ID":
            cur["recurrence_id"] = parse_dt(value, params, tz)[0].date()
        elif name in ("SUMMARY", "LOCATION", "DESCRIPTION", "UID", "STATUS"):
            cur[name.lower()] = _unescape(value)
    for ev in events:
        if "end" not in ev:
            default = timedelta(days=1) if ev.get("all_day") else timedelta(0)
            ev["end"] = ev["start"] + ev.pop("duration", default)
    return events


def _parse_duration(value: str) -> timedelta:
    import re

    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value.strip())
    if not m:
        return timedelta(0)
    sign, w, d, h, mi, s = m.groups()
    td = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0), seconds=int(s or 0))
    return -td if sign == "-" else td


def _matches_rule(rule: dict[str, str], start: date, day: date) -> bool:
    interval = int(rule.get("INTERVAL", 1))
    freq = rule.get("FREQ", "").upper()
    if freq == "DAILY":
        return (day - start).days % interval == 0
    if freq == "WEEKLY":
        days = [WEEKDAYS[d[-2:]] for d in rule.get("BYDAY", "").split(",") if d[-2:] in WEEKDAYS] or [start.weekday()]
        weeks = ((day - timedelta(days=day.weekday())) - (start - timedelta(days=start.weekday()))).days // 7
        return day.weekday() in days and weeks % interval == 0
    if freq == "MONTHLY":
        months = (day.year - start.year) * 12 + day.month - start.month
        return day.day == start.day and months % interval == 0
    if freq == "YEARLY":
        return (day.month, day.day) == (start.month, start.day) and (day.year - start.year) % interval == 0
    return False


def occurs_on(ev: dict[str, Any], day: date) -> bool:
    start = ev["start"].date()
    rule = ev.get("rrule")
    if not rule:
        return False
    if day < start or day in ev["exdates"] or not _matches_rule(rule, start, day):
        return False
    if "UNTIL" in rule and day > datetime.strptime(rule["UNTIL"][:8], "%Y%m%d").date():
        return False
    if "COUNT" in rule:
        n = sum(_matches_rule(rule, start, start + timedelta(days=i)) for i in range((day - start).days + 1))
        return n <= int(rule["COUNT"])
    return True


def events_for_day(text: str, day: date, tz: tzinfo, source: str = "") -> list[Event]:
    raw = [e for e in parse_events(text, tz) if e.get("status", "").upper() != "CANCELLED"]
    overridden = {(e.get("uid"), e["recurrence_id"]) for e in raw if "recurrence_id" in e}
    day_start = datetime.combine(day, time(), tz)
    day_end = day_start + timedelta(days=1)
    out: list[Event] = []
    for ev in raw:
        start, end = ev["start"], ev["end"]
        if ev.get("rrule"):
            if not occurs_on(ev, day) or (ev.get("uid"), day) in overridden:
                continue
            length = end - start
            start = datetime.combine(day, start.timetz()) if not ev["all_day"] else day_start
            end = start + length
        elif not (start < day_end and end > day_start) and not (start == end and day_start <= start < day_end):
            continue
        out.append(
            Event(
                title=ev.get("summary", "(no title)"),
                start=start,
                end=end,
                all_day=ev.get("all_day", False),
                location=ev.get("location", ""),
                description=ev.get("description", "")[:300],
                source=source,
            )
        )
    return out


@register
class ICSCalendar(Connector):
    """``type = "ics"`` — options: ``source`` (path or URL)."""

    type = "ics"
    kind = "calendar"

    def fetch(self, day: date) -> list[Event]:
        text = self.read_text(self.option("source", required=True))
        return events_for_day(text, day, self.config.tz, source=self.name)
