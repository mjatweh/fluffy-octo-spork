"""CalDAV calendars (stdlib ``urllib`` + ``xml.etree``), with an iCloud preset.

Reads every calendar your account can see — including calendars other people
share with you, such as a family calendar someone else owns — without making
anything public. For iCloud, sign in with your Apple ID and an app-specific
password (account.apple.com → Sign-In and Security → App-Specific Passwords).

Read-only: only PROPFIND and REPORT requests are sent.
"""
from __future__ import annotations

import base64
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone

from ..models import Event
from .. import tls
from .base import Connector, ConnectorError, register
from .ics import events_for_day

NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
ICLOUD = "https://caldav.icloud.com"

PRINCIPAL = '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
HOME = ('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        "<d:prop><c:calendar-home-set/></d:prop></d:propfind>")
LIST = '<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/><d:resourcetype/></d:prop></d:propfind>'
QUERY = """<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><c:calendar-data/></d:prop>
  <c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">
    <c:time-range start="{start}" end="{end}"/>
  </c:comp-filter></c:comp-filter></c:filter>
</c:calendar-query>"""


def parse_multistatus(xml_text: str) -> list[ET.Element]:
    try:
        return ET.fromstring(xml_text).findall("d:response", NS)
    except ET.ParseError as exc:
        raise ConnectorError(f"CalDAV server returned invalid XML: {exc}") from exc


def first_href(xml_text: str, prop: str) -> str:
    for resp in parse_multistatus(xml_text):
        href = resp.find(f".//{prop}/d:href", NS)
        if href is not None and href.text:
            return href.text.strip()
    raise ConnectorError(f"CalDAV server did not report {prop}")


def list_calendars(xml_text: str) -> list[tuple[str, str]]:
    """``(href, display name)`` for every calendar collection in a PROPFIND reply."""
    out = []
    for resp in parse_multistatus(xml_text):
        if resp.find(".//d:resourcetype/c:calendar", NS) is None:
            continue
        href = resp.findtext("d:href", "", NS).strip()
        out.append((href, (resp.findtext(".//d:displayname", "", NS) or "").strip() or href))
    return out


def calendar_data(xml_text: str) -> list[str]:
    return [el.text for el in ET.fromstring(xml_text).iterfind(".//c:calendar-data", NS) if el.text]


@register
class CalDAVCalendar(Connector):
    """``type = "caldav"`` — options: ``server``, ``username``, ``password_env``,
    ``calendars`` (list of display names to include; default all)."""

    type = "caldav"
    kind = "calendar"
    default_server = ""

    def _send(self, url: str, method: str, body: str, depth: str) -> tuple[str, str]:
        """Send a WebDAV request, following redirects by hand (urllib only redirects GET/POST).
        Returns ``(final url, response text)``."""
        creds = base64.b64encode(f"{self.option('username', required=True)}:{self.secret('password')}".encode())
        for _ in range(5):
            req = urllib.request.Request(url, data=body.encode(), method=method, headers={
                "Authorization": f"Basic {creds.decode()}", "Depth": depth,
                "Content-Type": "application/xml; charset=utf-8", "User-Agent": "life-dashboard/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=20, context=tls.context()) as resp:
                    return resp.geturl(), resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 307, 308) and exc.headers.get("Location"):
                    url = urllib.parse.urljoin(url, exc.headers["Location"])
                    continue
                if exc.code == 401:
                    raise ConnectorError(f"{self.name}: sign-in rejected; check username and app-specific password") from exc
                raise ConnectorError(f"{self.name}: CalDAV {method} failed: HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                raise ConnectorError(f"{self.name}: can't reach {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from exc
        raise ConnectorError(f"{self.name}: too many redirects")

    def calendars(self) -> list[tuple[str, str]]:
        server = self.option("server", self.default_server or None, required=True)
        url, reply = self._send(server.rstrip("/") + "/", "PROPFIND", PRINCIPAL, "0")
        principal = urllib.parse.urljoin(url, first_href(reply, "d:current-user-principal"))
        url, reply = self._send(principal, "PROPFIND", HOME, "0")
        home = urllib.parse.urljoin(url, first_href(reply, "c:calendar-home-set"))
        url, reply = self._send(home, "PROPFIND", LIST, "1")
        found = [(urllib.parse.urljoin(url, href), name) for href, name in list_calendars(reply)]
        wanted = self.option("calendars")
        if wanted:
            names = {str(w).casefold() for w in wanted}
            chosen = [c for c in found if c[1].casefold() in names]
            if not chosen:
                raise ConnectorError(f"{self.name}: none of {list(wanted)} found; available: "
                                     + ", ".join(n for _, n in found))
            return chosen
        return found

    def fetch(self, day: date) -> list[Event]:
        return self.fetch_days(day, 1)

    def fetch_days(self, first: date, days: int) -> list[Event]:
        """Events from ``first`` for ``days`` days, with one query per calendar. An event that spans
        several days is returned once."""
        start = datetime.combine(first, time(), self.config.tz).astimezone(timezone.utc)
        rng = {k: v.strftime("%Y%m%dT%H%M%SZ") for k, v in {"start": start, "end": start + timedelta(days=days)}.items()}
        events: list[Event] = []
        seen: set[tuple] = set()
        for href, cal_name in self.calendars():
            _, reply = self._send(href, "REPORT", QUERY.format(**rng), "1")
            for ics in calendar_data(reply):
                for offset in range(days):
                    for ev in events_for_day(ics, first + timedelta(days=offset), self.config.tz,
                                             source=f"{self.name}: {cal_name}"):
                        key = (ev.title, ev.start, ev.end)
                        if key not in seen:
                            seen.add(key)
                            events.append(ev)
        return events


@register
class ICloudCalendar(CalDAVCalendar):
    """``type = "icloud"`` — CalDAV preset for iCloud: ``username`` (Apple ID email),
    ``password_env`` (app-specific password), ``calendars`` (e.g. ``["MCM"]``)."""

    type = "icloud"
    default_server = ICLOUD
