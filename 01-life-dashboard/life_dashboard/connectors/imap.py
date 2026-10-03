"""IMAP email connector (stdlib ``imaplib``). Works with Gmail/Fastmail/iCloud
app passwords. Fetches recent messages read-only (``BODY.PEEK`` — nothing is
marked as read)."""
from __future__ import annotations

import email
import imaplib
import re
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from ..models import Email
from .base import Connector, ConnectorError, register


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _text_snippet(msg: email.message.Message, limit: int = 240) -> str:
    part = msg
    if msg.is_multipart():
        part = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None)
        if part is None:
            return ""
    payload = part.get_payload(decode=True) or b""
    text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def parse_message(raw: bytes, flags: bytes, source: str, tz) -> Email:
    msg = email.message_from_bytes(raw)
    name, addr = parseaddr(_decode(msg.get("From")))
    try:
        received = parsedate_to_datetime(msg.get("Date")).astimezone(tz)
    except Exception:
        received = datetime.now(tz)
    return Email(
        sender=f"{name} <{addr}>" if name else addr,
        subject=_decode(msg.get("Subject")) or "(no subject)",
        received=received,
        snippet=_text_snippet(msg),
        unread=b"\\Seen" not in flags,
        flagged=b"\\Flagged" in flags,
        source=source,
    )


@register
class IMAPEmail(Connector):
    """``type = "imap"`` — options: ``host``, ``username``, ``password_env``,
    ``mailbox`` (INBOX), ``days`` (2), ``unread_only`` (true), ``limit`` (25)."""

    type = "imap"
    kind = "email"

    def fetch(self, day: date) -> list[Email]:
        host = self.option("host", required=True)
        user = self.option("username", required=True)
        password = self.secret("password")
        since = (day - timedelta(days=int(self.option("days", 2)))).strftime("%d-%b-%Y")
        criteria = f"(UNSEEN SINCE {since})" if self.option("unread_only", True) else f"(SINCE {since})"
        limit = int(self.option("limit", 25))
        try:
            with imaplib.IMAP4_SSL(host, int(self.option("port", 993))) as conn:
                conn.login(user, password)
                conn.select(self.option("mailbox", "INBOX"), readonly=True)
                _, data = conn.search(None, criteria)
                ids = data[0].split()[-limit:]
                out = []
                for msg_id in reversed(ids):
                    _, parts = conn.fetch(msg_id, "(FLAGS BODY.PEEK[])")
                    meta, raw = parts[0]
                    flags = b" ".join(imaplib.ParseFlags(meta))
                    out.append(parse_message(raw, flags, self.name, self.config.tz))
                return out
        except imaplib.IMAP4.error as exc:
            raise ConnectorError(f"{self.name}: IMAP error: {exc}") from exc
