import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from life_dashboard.google_calendar import GoogleCalendar, GoogleError, event_id, mirror, to_google
from life_dashboard.models import Event

NY = ZoneInfo("America/New_York")


def ev(title, day, hour=10, all_day=False):
    start = datetime(2026, 10, day, hour, tzinfo=NY)
    return Event(title=title, start=start, end=start.replace(hour=hour + 1), all_day=all_day)


class FakeGoogle:
    """Records calls to the Google API and serves a tiny in-memory calendar."""

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.deleted: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method, url, body=None, token=None, form=None, timeout=30):
        self.calls.append((method, url))
        if url.endswith("/token"):
            return {"access_token": "at", "expires_in": 3600}
        if method == "POST" and url.endswith("/calendars"):
            return {"id": "cal1"}
        if method == "GET" and "/events?" in url:
            return {"items": [{"id": i} for i in self.events]}
        if method == "POST" and url.endswith("/events"):
            if body["id"] in self.events or body["id"] in self.deleted:
                raise GoogleError("exists", 409)
            self.events[body["id"]] = body
            return body
        if method == "PUT":
            self.events[body["id"]] = body
            self.deleted.discard(body["id"])
            return body
        if method == "DELETE":
            ev_id = url.rsplit("/", 1)[1]
            self.events.pop(ev_id)
            self.deleted.add(ev_id)
            return {}
        if method == "GET":
            return {"id": "cal1"}
        raise AssertionError(f"unexpected {method} {url}")


@pytest.fixture
def google(tmp_path):
    fake = FakeGoogle()
    g = GoogleCalendar("id", "secret", token_file=tmp_path / "google.json", call=fake)
    g._save({"refresh_token": "rt"})
    return g, fake


def test_event_ids_are_valid_and_stable():
    a, b = ev("Dinner", 10), ev("Dinner", 10)
    assert event_id(a) == event_id(b) != event_id(ev("Dinner", 11))
    assert re.fullmatch(r"[0-9a-v]{5,1024}", event_id(a))


def test_all_day_events_use_dates():
    e = ev("Trip", 10, all_day=True)
    body = to_google(e, "America/New_York")
    assert body["start"] == {"date": "2026-10-10"} and body["end"] == {"date": "2026-10-11"}
    timed = to_google(ev("Call", 10), "America/New_York")
    assert timed["start"]["timeZone"] == "America/New_York"


def test_mirror_adds_removes_and_is_idempotent(google):
    g, fake = google
    first = [ev("Dinner", 10), ev("Brunch", 11)]
    assert mirror(first, g, "MCM (copy)", "America/New_York", date(2026, 10, 9), 60) == (2, 0)
    assert mirror(first, g, "MCM (copy)", "America/New_York", date(2026, 10, 9), 60) == (0, 0)
    # Brunch moved to the 12th: old copy removed, new one added
    second = [ev("Dinner", 10), ev("Brunch", 12)]
    assert mirror(second, g, "MCM (copy)", "America/New_York", date(2026, 10, 9), 60) == (1, 1)
    assert sorted(e["summary"] for e in fake.events.values()) == ["Brunch", "Dinner"]
    # moved back: the id existed before (deleted) -> restored with PUT
    assert mirror(first, g, "MCM (copy)", "America/New_York", date(2026, 10, 9), 60) == (1, 1)
    assert any(m == "PUT" for m, _ in fake.calls)
    # the copy calendar was created once and remembered
    assert sum(1 for m, u in fake.calls if m == "POST" and u.endswith("/calendars")) == 1
    assert json.loads(g.token_file.read_text())["calendars"] == {"MCM (copy)": "cal1"}


def test_token_file_is_private(google):
    g, _ = google
    assert g.token_file.stat().st_mode & 0o777 == 0o600


def test_not_signed_in(tmp_path):
    g = GoogleCalendar("id", "secret", token_file=tmp_path / "none.json", call=FakeGoogle())
    assert not g.signed_in
    with pytest.raises(GoogleError, match="mirror auth"):
        g.token()


def test_missing_client_details():
    with pytest.raises(GoogleError, match="GOOGLE_CLIENT_ID"):
        GoogleCalendar("", "")
