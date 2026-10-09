"""Copy a calendar the Claude app can't read (e.g. a shared iCloud calendar) into Google Calendar.

``python -m life_dashboard mirror auth`` signs in to Google once in the browser; ``python -m
life_dashboard mirror`` then copies the next N days of one connector's events into a separate
calendar ("MCM (copy)") in that Google account. Run it on a schedule and the copy stays current;
the Claude app, which reads your Google Calendar, can then answer questions about it.

The copy is one-way and only touches the calendar it created: the permission requested
(``calendar.app.created``) lets it manage calendars this app made and nothing else.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Callable

from . import tls
from .models import Event

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
DEFAULT_SCOPE = "https://www.googleapis.com/auth/calendar.app.created"
STATE_DIR = Path("~/.config/life-dashboard").expanduser()


class GoogleError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _call(method: str, url: str, body: dict | None = None, token: str | None = None,
          form: dict | None = None, timeout: float = 30) -> dict:
    headers = {"User-Agent": "life-dashboard/1.0", "Accept": "application/json"}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=tls.context()) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            err = json.loads(detail)
            err = err.get("error_description") or err.get("error", {}).get("message") or err.get("error") or detail
        except ValueError:
            err = detail[:200]
        raise GoogleError(f"Google: HTTP {exc.code}: {err}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise GoogleError(f"can't reach {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from exc
    return json.loads(raw) if raw else {}


def event_id(ev: Event) -> str:
    """Stable Google event id (base32hex: 0-9, a-v) from what the event looks like, so re-running
    the copy never duplicates and an edited event gets replaced."""
    key = "|".join([ev.title, ev.start.isoformat(), ev.end.isoformat(), str(ev.all_day), ev.location, ev.description])
    return "mcm" + hashlib.sha1(key.encode()).hexdigest()


def to_google(ev: Event, tz_name: str) -> dict:
    if ev.all_day:
        end = ev.end.date() if ev.end.date() > ev.start.date() else ev.start.date() + timedelta(days=1)
        when = {"start": {"date": ev.start.date().isoformat()}, "end": {"date": end.isoformat()}}
    else:
        when = {"start": {"dateTime": ev.start.isoformat(), "timeZone": tz_name},
                "end": {"dateTime": ev.end.isoformat(), "timeZone": tz_name}}
    return {"id": event_id(ev), "summary": ev.title, "location": ev.location, "description": ev.description,
            "status": "confirmed", **when}


class GoogleCalendar:
    def __init__(self, client_id: str, client_secret: str, token_file: Path | None = None,
                 scope: str | None = None, call: Callable[..., dict] = _call):
        if not client_id or not client_secret:
            raise GoogleError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set (see `setup_wizard.py --only google`)")
        self.client_id, self.client_secret = client_id, client_secret
        self.token_file = token_file or STATE_DIR / "google-calendar.json"
        self.scope = scope or os.environ.get("GOOGLE_CALENDAR_SCOPE") or DEFAULT_SCOPE
        self.call = call
        self._access: tuple[str, float] | None = None

    @classmethod
    def from_env(cls) -> "GoogleCalendar":
        return cls(os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_SECRET", ""))

    # -- sign-in ---------------------------------------------------------------------------------
    def _save(self, data: dict) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)

    def _state(self) -> dict:
        try:
            return json.loads(self.token_file.read_text())
        except (OSError, ValueError):
            return {}

    @property
    def signed_in(self) -> bool:
        return bool(self._state().get("refresh_token"))

    def login(self, say: Callable[[str], None] = print, open_browser: Callable[[str], Any] = webbrowser.open,
              timeout: float = 300) -> None:
        """Browser sign-in with a one-shot local web server (Google's flow for desktop apps)."""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        result: dict[str, str] = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
                if query.get("state") == state:
                    result.update(query)
                ok = "code" in query
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(("<h2>Done. You can close this tab and go back to the Terminal.</h2>" if ok else
                                  "<h2>Sign-in didn't finish. Go back to the Terminal.</h2>").encode())

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        server.timeout = timeout
        redirect = f"http://127.0.0.1:{server.server_port}"
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id, "redirect_uri": redirect, "response_type": "code", "scope": self.scope,
            "access_type": "offline", "prompt": "consent", "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        say(f"Opening Google sign-in in your browser. If it doesn't open, paste this link:\n{url}")
        open_browser(url)
        worker = threading.Thread(target=server.handle_request, daemon=True)
        worker.start()
        worker.join(timeout)
        server.server_close()
        if "code" not in result:
            raise GoogleError(f"Google sign-in didn't finish ({result.get('error', 'no answer within 5 minutes')})")
        tokens = self.call("POST", TOKEN_URL, form={
            "client_id": self.client_id, "client_secret": self.client_secret, "code": result["code"],
            "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect})
        if not tokens.get("refresh_token"):
            raise GoogleError("Google didn't return a refresh token; run the sign-in again")
        self._save({**self._state(), "refresh_token": tokens["refresh_token"], "scope": self.scope})

    def token(self) -> str:
        if self._access and self._access[1] > time.time() + 60:
            return self._access[0]
        refresh = self._state().get("refresh_token")
        if not refresh:
            raise GoogleError("not signed in to Google yet; run `python -m life_dashboard mirror auth`")
        try:
            data = self.call("POST", TOKEN_URL, form={"client_id": self.client_id, "client_secret": self.client_secret,
                                                      "refresh_token": refresh, "grant_type": "refresh_token"})
        except GoogleError as exc:
            if exc.status in (400, 401):
                raise GoogleError("Google sign-in expired or was revoked; run `python -m life_dashboard mirror auth`",
                                  exc.status) from exc
            raise
        self._access = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
        return self._access[0]

    # -- calendar --------------------------------------------------------------------------------
    def ensure_calendar(self, name: str, tz_name: str) -> str:
        """The id of the copy calendar, creating it the first time."""
        state = self._state()
        ids = state.get("calendars", {})
        if ids.get(name):
            try:
                self.call("GET", f"{API}/calendars/{urllib.parse.quote(ids[name])}", token=self.token())
                return ids[name]
            except GoogleError as exc:
                if exc.status not in (403, 404):
                    raise
        created = self.call("POST", f"{API}/calendars", {"summary": name, "timeZone": tz_name,
                                                         "description": "Copied automatically; edits here are overwritten."},
                            token=self.token())
        ids[name] = created["id"]
        self._save({**self._state(), "calendars": ids})
        return created["id"]

    def list_ids(self, calendar_id: str, start: datetime, end: datetime) -> set[str]:
        ids: set[str] = set()
        params = {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "maxResults": "2500", "showDeleted": "false"}
        base = f"{API}/calendars/{urllib.parse.quote(calendar_id)}/events"
        while True:
            page = self.call("GET", base + "?" + urllib.parse.urlencode(params), token=self.token())
            ids |= {item["id"] for item in page.get("items", []) if item.get("status") != "cancelled"}
            if not page.get("nextPageToken"):
                return ids
            params["pageToken"] = page["nextPageToken"]

    def put_event(self, calendar_id: str, body: dict) -> None:
        base = f"{API}/calendars/{urllib.parse.quote(calendar_id)}/events"
        try:
            self.call("POST", base, body, token=self.token())
        except GoogleError as exc:
            if exc.status != 409:  # 409: the id exists (e.g. deleted earlier) -> bring it back
                raise
            self.call("PUT", f"{base}/{body['id']}", body, token=self.token())

    def delete_event(self, calendar_id: str, ev_id: str) -> None:
        try:
            self.call("DELETE", f"{API}/calendars/{urllib.parse.quote(calendar_id)}/events/{ev_id}", token=self.token())
        except GoogleError as exc:
            if exc.status not in (404, 410):
                raise


def mirror(events: list[Event], google: GoogleCalendar, calendar_name: str, tz_name: str,
           start: date, days: int) -> tuple[int, int]:
    """Make the copy calendar match ``events`` in the window. Returns ``(added, removed)``."""
    cal = google.ensure_calendar(calendar_name, tz_name)
    window_start = datetime.combine(start, datetime.min.time(), ZoneInfo(tz_name))  # earlier events are left alone
    window_end = window_start + timedelta(days=days)
    wanted = {event_id(ev): ev for ev in events}
    existing = google.list_ids(cal, window_start, window_end)
    for ev_id in sorted(set(wanted) - existing):
        google.put_event(cal, to_google(wanted[ev_id], tz_name))
    for ev_id in sorted(existing - set(wanted)):
        google.delete_event(cal, ev_id)
    return len(set(wanted) - existing), len(existing - set(wanted))
