import html
import io
import urllib.error
from email.message import Message

import pytest

from life_dashboard.connectors import ConnectorError, build_connector
from life_dashboard.connectors import caldav

PRINCIPAL_XML = """<d:multistatus xmlns:d="DAV:"><d:response><d:href>/</d:href><d:propstat><d:prop>
<d:current-user-principal><d:href>/123456/principal/</d:href></d:current-user-principal>
</d:prop></d:propstat></d:response></d:multistatus>"""

HOME_XML = """<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response>
<d:href>/123456/principal/</d:href><d:propstat><d:prop><c:calendar-home-set>
<d:href>https://p42-caldav.icloud.com:443/123456/calendars/</d:href>
</c:calendar-home-set></d:prop></d:propstat></d:response></d:multistatus>"""

LIST_XML = """<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
<d:response><d:href>/123456/calendars/</d:href><d:propstat><d:prop>
  <d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/123456/calendars/home/</d:href><d:propstat><d:prop><d:displayname>Home</d:displayname>
  <d:resourcetype><d:collection/><c:calendar/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/123456/calendars/shared-mcm/</d:href><d:propstat><d:prop><d:displayname>MCM</d:displayname>
  <d:resourcetype><d:collection/><c:calendar/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/123456/calendars/tasks/</d:href><d:propstat><d:prop><d:displayname>Reminders</d:displayname>
  <d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
</d:multistatus>"""

EVENT_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:fo-1
DTSTART;TZID=America/New_York:20261005T100000
DTEND;TZID=America/New_York:20261005T110000
SUMMARY:Family office investment committee
LOCATION:Charles's office
END:VEVENT
END:VCALENDAR"""

WEEKLY_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:fo-2
DTSTART;TZID=America/New_York:20260928T080000
DTEND;TZID=America/New_York:20260928T083000
RRULE:FREQ=WEEKLY;BYDAY=MO
SUMMARY:Weekly sync with Mark & Michael
END:VEVENT
END:VCALENDAR"""


def report_xml(*calendars):
    items = "".join(f"<d:response><d:href>/e{i}.ics</d:href><d:propstat><d:prop><c:calendar-data>{html.escape(c)}</c:calendar-data>"
                    f"</d:prop></d:propstat></d:response>" for i, c in enumerate(calendars))
    return f'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">{items}</d:multistatus>'


@pytest.fixture
def conn(config, monkeypatch):
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "abcd-efgh-ijkl-mnop")
    return build_connector({"type": "icloud", "name": "iCloud", "username": "me@icloud.com",
                            "password_env": "ICLOUD_APP_PASSWORD", "calendars": ["mcm"]}, config)


def fake_server(calls):
    def send(url, method, body, depth):
        calls.append((url, method, depth))
        if method == "REPORT":
            assert url.endswith("/shared-mcm/")
            assert 'start="20261005T040000Z" end="20261006T040000Z"' in body
            return url, report_xml(EVENT_ICS, WEEKLY_ICS)
        if "current-user-principal" in body:
            return url, PRINCIPAL_XML
        if "calendar-home-set" in body:
            return url, HOME_XML
        return url, LIST_XML
    return send


def test_registered():
    from life_dashboard.connectors import REGISTRY

    assert REGISTRY["icloud"].kind == REGISTRY["caldav"].kind == "calendar"


def test_list_calendars_keeps_only_calendar_collections():
    assert caldav.list_calendars(LIST_XML) == [("/123456/calendars/home/", "Home"),
                                                ("/123456/calendars/shared-mcm/", "MCM")]


def test_fetch_discovers_shared_calendar_and_expands_events(conn, day, monkeypatch):
    calls = []
    monkeypatch.setattr(conn, "_send", fake_server(calls))
    events = sorted(conn.fetch(day), key=lambda e: e.start)
    assert [e.title for e in events] == ["Weekly sync with Mark & Michael", "Family office investment committee"]
    assert events[0].start.hour == 8 and events[1].location == "Charles's office"
    assert events[1].source == "iCloud: MCM"
    # discovery follows the principal → home (on the pXX host) → list chain, then one REPORT for MCM only
    assert calls[0] == ("https://caldav.icloud.com/", "PROPFIND", "0")
    assert calls[1][0] == "https://caldav.icloud.com/123456/principal/"
    assert calls[2][0] == "https://p42-caldav.icloud.com:443/123456/calendars/"
    assert [c[1] for c in calls].count("REPORT") == 1


def test_unknown_calendar_name_lists_available(conn, day, monkeypatch):
    conn.options["calendars"] = ["Work"]
    monkeypatch.setattr(conn, "_send", fake_server([]))
    with pytest.raises(ConnectorError, match="available: Home, MCM"):
        conn.fetch(day)


def test_send_follows_redirects_and_sends_basic_auth(conn, monkeypatch):
    seen = []

    class Resp(io.BytesIO):
        def geturl(self):
            return seen[-1].full_url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=20, context=None):
        seen.append(req)
        if len(seen) == 1:
            headers = Message()
            headers["Location"] = "https://p42-caldav.icloud.com/"
            raise urllib.error.HTTPError(req.full_url, 301, "Moved", headers, None)
        return Resp(PRINCIPAL_XML.encode())

    monkeypatch.setattr(caldav.urllib.request, "urlopen", urlopen)
    url, text = conn._send("https://caldav.icloud.com/", "PROPFIND", caldav.PRINCIPAL, "0")
    assert url == "https://p42-caldav.icloud.com/" and "principal" in text
    assert seen[1].get_method() == "PROPFIND" and seen[1].get_header("Depth") == "0"
    assert seen[1].get_header("Authorization").startswith("Basic ")


def test_wrong_password_message(conn, monkeypatch):
    def urlopen(req, timeout=20, context=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", Message(), None)

    monkeypatch.setattr(caldav.urllib.request, "urlopen", urlopen)
    with pytest.raises(ConnectorError, match="app-specific password"):
        conn._send("https://caldav.icloud.com/", "PROPFIND", caldav.PRINCIPAL, "0")


def test_missing_password_env(config, day, monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    c = build_connector({"type": "icloud", "username": "me@icloud.com", "password_env": "NOPE"}, config)
    with pytest.raises(ConnectorError, match="NOPE"):
        c.fetch(day)
