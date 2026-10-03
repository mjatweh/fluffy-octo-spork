"""Outlook / Microsoft 365 email via Microsoft Graph (stdlib ``urllib``).

Microsoft no longer allows app passwords over IMAP, so this uses OAuth with the
device-code flow: run ``python -m life_dashboard auth`` once, open the link it
prints, enter the code, and sign in. The refresh token is cached locally
(``chmod 600``) and renewed on every fetch, so scheduled runs need no browser.

Read-only: the only permission requested is ``Mail.Read`` (+ ``offline_access``
for the refresh token). Nothing is sent, moved, deleted, or marked as read.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from ..models import Email
from .base import Connector, ConnectorError, register

LOGIN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/{endpoint}"
GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = "offline_access Mail.Read"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
SELECT = "subject,from,receivedDateTime,bodyPreview,isRead,flag"


class OAuthError(ConnectorError):
    def __init__(self, code: str, description: str = ""):
        super().__init__(f"{code}: {description}".strip(": "))
        self.code = code


def _request(url: str, data: dict | None = None, token: str | None = None, timeout: float = 20) -> dict:
    """POST form data (when ``data`` is given) or GET with a bearer token; returns JSON.
    OAuth errors (``{"error": ...}`` bodies) are raised as :class:`OAuthError`."""
    headers = {"User-Agent": "life-dashboard/1.0", "Accept": "application/json"}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["Prefer"] = 'outlook.body-content-type="text"'
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            err = json.load(exc)
        except Exception:
            raise ConnectorError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}") from exc
        if isinstance(err.get("error"), dict):  # Graph style: {"error": {"code", "message"}}
            raise OAuthError(err["error"].get("code", str(exc.code)), err["error"].get("message", "")) from exc
        raise OAuthError(err.get("error", str(exc.code)), err.get("error_description", "").split("\r\n")[0]) from exc


def parse_messages(payload: dict, source: str, tz) -> list[Email]:
    out = []
    for m in payload.get("value", []):
        addr = (m.get("from") or {}).get("emailAddress") or {}
        name, mail = addr.get("name", ""), addr.get("address", "")
        try:
            received = datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")).astimezone(tz)
        except (KeyError, ValueError):
            received = datetime.now(tz)
        out.append(
            Email(
                sender=f"{name} <{mail}>" if name and name != mail else mail or name,
                subject=m.get("subject") or "(no subject)",
                received=received,
                snippet=re.sub(r"\s+", " ", m.get("bodyPreview") or "").strip()[:240],
                unread=not m.get("isRead", False),
                flagged=(m.get("flag") or {}).get("flagStatus") == "flagged",
                source=source,
            )
        )
    return out


@register
class OutlookEmail(Connector):
    """``type = "outlook"`` — options: ``client_id`` (or ``client_id_env``), ``tenant``
    (``common`` | ``consumers`` | ``organizations`` | a tenant id; default ``common``),
    ``folder`` (inbox), ``days`` (2), ``unread_only`` (true), ``limit`` (25),
    ``token_cache`` (default ``~/.config/life-dashboard/outlook-<name>.json``)."""

    type = "outlook"
    kind = "email"

    # -- config -----------------------------------------------------------
    @property
    def client_id(self) -> str:
        if self.options.get("client_id_env"):
            return self.secret("client_id")
        return self.option("client_id", required=True)

    @property
    def tenant(self) -> str:
        return self.option("tenant", "common")

    @property
    def token_cache(self) -> Path:
        if self.options.get("token_cache"):
            return self.config.resolve(self.options["token_cache"])
        slug = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-") or "outlook"
        return Path("~/.config/life-dashboard").expanduser() / f"outlook-{slug}.json"

    def _url(self, endpoint: str) -> str:
        return LOGIN.format(tenant=self.tenant, endpoint=endpoint)

    def _save(self, tokens: dict) -> None:
        path = self.token_cache
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({"refresh_token": tokens["refresh_token"], "client_id": self.client_id,
                       "tenant": self.tenant}, fh)

    # -- auth -------------------------------------------------------------
    def login(self, prompt: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep) -> Path:
        """Interactive device-code sign-in; caches the refresh token. Returns the cache path."""
        flow = _request(self._url("devicecode"), {"client_id": self.client_id, "scope": SCOPES})
        prompt(flow.get("message") or f"Open {flow['verification_uri']} and enter code {flow['user_code']}")
        interval = int(flow.get("interval", 5))
        deadline = time.monotonic() + int(flow.get("expires_in", 900))
        while time.monotonic() < deadline:
            sleep(interval)
            try:
                tokens = _request(self._url("token"), {"grant_type": DEVICE_GRANT, "client_id": self.client_id,
                                                       "device_code": flow["device_code"]})
            except OAuthError as exc:
                if exc.code == "authorization_pending":
                    continue
                if exc.code == "slow_down":
                    interval += 5
                    continue
                raise
            self._save(tokens)
            return self.token_cache
        raise ConnectorError(f"{self.name}: sign-in timed out; run `python -m life_dashboard auth` again")

    def access_token(self) -> str:
        client_id = self.client_id  # report a missing app id before "not signed in"
        path = self.token_cache
        if not path.is_file():
            raise ConnectorError(f"{self.name}: not signed in yet; run `python -m life_dashboard auth \"{self.name}\"`")
        cached = json.loads(path.read_text())
        try:
            tokens = _request(self._url("token"), {"grant_type": "refresh_token", "client_id": client_id,
                                                   "refresh_token": cached["refresh_token"], "scope": SCOPES})
        except OAuthError as exc:
            if exc.code in ("invalid_grant", "interaction_required"):
                raise ConnectorError(f"{self.name}: sign-in expired; run `python -m life_dashboard auth "
                                     f"\"{self.name}\"` again") from exc
            raise ConnectorError(f"{self.name}: token refresh failed: {exc}") from exc
        if tokens.get("refresh_token"):  # Microsoft rotates refresh tokens
            self._save(tokens)
        return tokens["access_token"]

    # -- fetch ------------------------------------------------------------
    def fetch(self, day: date) -> list[Email]:
        token = self.access_token()
        start = datetime.combine(day - timedelta(days=int(self.option("days", 2))), datetime.min.time(),
                                 self.config.tz).astimezone(timezone.utc)
        flt = f"receivedDateTime ge {start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        if self.option("unread_only", True):
            flt += " and isRead eq false"
        query = urllib.parse.urlencode({"$filter": flt, "$orderby": "receivedDateTime desc",
                                        "$top": int(self.option("limit", 25)), "$select": SELECT})
        folder = urllib.parse.quote(self.option("folder", "inbox"))
        try:
            payload = _request(f"{GRAPH}/me/mailFolders/{folder}/messages?{query}", token=token)
        except OAuthError as exc:
            raise ConnectorError(f"{self.name}: Microsoft Graph error {exc}") from exc
        return parse_messages(payload, self.name, self.config.tz)
