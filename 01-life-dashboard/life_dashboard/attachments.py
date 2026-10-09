"""Import important email attachments into the Second Brain.

Reads the inboxes already configured for the dashboard (IMAP and Outlook), picks PDF and Word
attachments from emails that match the rules in ``attachments.toml`` at the repo root (private,
gitignored; see ``attachments.example.toml``), and
saves them to ``<vault>/00 Inbox`` for ``python -m second_brain ingest`` to file. Read-only on the
mail side: messages are fetched with BODY.PEEK / Graph GETs, so nothing is marked read, moved or
deleted. Message ids already imported are remembered, so a daily run only picks up new mail.

    days = 365                       # how far back the first run looks
    extensions = ["pdf", "docx", "doc"]

    [[rules]]
    name = "Insurance"
    senders = ["morrowinsurance.com", "agent@example.com"]   # domain or full address
    keywords = ["policy", "renewal", "certificate of insurance"]  # subject or file name
    inboxes = ["Personal Gmail"]     # optional: limit to these connector names
"""
from __future__ import annotations

import base64
import email
import hashlib
import imaplib
import json
import logging
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

from . import tls
from .config import PROJECT_DIR, Config
from .connectors import ConnectorError, build_connector
from .connectors.imap import _decode

log = logging.getLogger(__name__)

RULES_FILE = PROJECT_DIR.parent / "attachments.toml"
STATE_FILE = Path("~/.config/life-dashboard/attachments-seen.json").expanduser()
DEFAULT_EXTENSIONS = ("pdf", "docx", "doc")
MAX_BYTES = 25 * 1024 * 1024
MAX_PER_RUN = 200
GMAIL_ALL = '"[Gmail]/All Mail"'


@dataclass
class Rule:
    name: str
    senders: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    inboxes: list[str] = field(default_factory=list)

    def matches(self, inbox: str, sender: str, text: str) -> bool:
        if self.inboxes and inbox not in self.inboxes:
            return False
        addr = sender.lower()
        domain = addr.rsplit("@", 1)[-1]
        for s in self.senders:
            s = s.lower().lstrip("@")
            if addr == s or ("@" not in s and (domain == s or domain.endswith("." + s))):
                return True
        low = text.lower()
        return any(re.search(r"(?<![a-z0-9])" + re.escape(k.lower()) + r"(?![a-z0-9])", low) for k in self.keywords)


@dataclass
class Found:
    inbox: str
    message_id: str
    sender: str
    subject: str
    received: datetime
    files: list[tuple[str, bytes]]
    rule: str = ""


def load_rules(settings: dict) -> list[Rule]:
    return [Rule(name=r.get("name", f"rule {i + 1}"), senders=list(r.get("senders", [])),
                 keywords=list(r.get("keywords", [])), inboxes=list(r.get("inboxes", [])))
            for i, r in enumerate(settings.get("rules", []))]


def first_match(rules: list[Rule], inbox: str, sender: str, subject: str, names: Iterable[str] = ()) -> Rule | None:
    text = " ".join([subject, *names])
    return next((r for r in rules if r.matches(inbox, sender, text)), None)


def wanted(name: str, size: int, extensions: Iterable[str]) -> bool:
    return bool(name) and name.rsplit(".", 1)[-1].lower() in set(extensions) and 0 < size <= MAX_BYTES


def files_from_message(msg: email.message.Message, extensions: Iterable[str]) -> list[tuple[str, bytes]]:
    out = []
    for part in msg.walk():
        name = _decode(part.get_filename())
        if not name or part.is_multipart():
            continue
        data = part.get_payload(decode=True) or b""
        if wanted(name, len(data), extensions):
            out.append((name, data))
    return out


def safe_name(name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"\s+", " ", re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", stem)).strip(" .")[:150] or "attachment"
    ext = re.sub(r"[^A-Za-z0-9]", "", ext)
    return f"{stem}.{ext}" if ext else stem


def save(found: Found, folder: Path) -> list[Path]:
    """Write the attachments as ``YYYY-MM-DD <name>``; identical files are not written twice."""
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for name, data in found.files:
        path = folder / f"{found.received:%Y-%m-%d} {safe_name(name)}"
        if path.exists():
            if path.read_bytes() == data:
                continue
            path = path.with_name(f"{path.stem} {hashlib.sha1(data).hexdigest()[:6]}{path.suffix}")
        path.write_bytes(data)
        saved.append(path)
    return saved


def load_seen(path: Path = STATE_FILE) -> dict[str, list[str]]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_seen(seen: dict[str, list[str]], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: sorted(set(v))[-5000:] for k, v in seen.items()}))


# -- sources ---------------------------------------------------------------------------------------

def imap_scan(conn: Any, options: dict, password: str, rules: list[Rule], seen: set[str], since: datetime,
              extensions: Iterable[str], tz) -> list[Found]:
    """Find matching messages in one IMAP account. ``conn`` is an ``imaplib.IMAP4_SSL``-like object."""
    name, host = options.get("name", "imap"), options.get("host", "")
    conn.login(options["username"], password)
    gmail = "gmail" in host or "googlemail" in host
    conn.select(options.get("attachments_mailbox", GMAIL_ALL if gmail else "INBOX"), readonly=True)
    if gmail:
        days = max(1, (datetime.now(timezone.utc) - since).days)
        exts = " OR ".join(f"filename:{e}" for e in extensions)
        typ, data = conn.uid("SEARCH", "X-GM-RAW", f'"has:attachment newer_than:{days}d ({exts})"')
    else:
        typ, data = conn.uid("SEARCH", None, f"SINCE {since:%d-%b-%Y}")
    uids = (data[0] or b"").split() if typ == "OK" else []
    found: list[Found] = []
    for uid in reversed(uids):  # newest first
        _, parts = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
        if not parts or not isinstance(parts[0], tuple):
            continue
        head = email.message_from_bytes(parts[0][1])
        msg_id = (head.get("Message-ID") or f"{name}:{uid.decode()}").strip()
        if msg_id in seen:
            continue
        sender = parseaddr(_decode(head.get("From")))[1]
        subject = _decode(head.get("Subject"))
        rule = first_match(rules, name, sender, subject)
        if rule is None:
            # the file name may be what matches ("Policy.pdf"), so look at the full message
            _, parts = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            msg = email.message_from_bytes(parts[0][1])
            files = files_from_message(msg, extensions)
            rule = first_match(rules, name, sender, subject, [f for f, _ in files]) if files else None
            if rule is None:
                seen.add(msg_id)  # never matches later either
                continue
        else:
            _, parts = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            msg = email.message_from_bytes(parts[0][1])
            files = files_from_message(msg, extensions)
        try:
            received = parsedate_to_datetime(head.get("Date")).astimezone(tz)
        except Exception:
            received = datetime.now(tz)
        if files:
            found.append(Found(name, msg_id, sender, subject, received, files, rule.name))
        else:
            seen.add(msg_id)
        if len(found) >= MAX_PER_RUN:
            break
    return found


def graph_scan(request, token: str, inbox: str, rules: list[Rule], seen: set[str], since: datetime,
               extensions: Iterable[str], tz) -> list[Found]:
    """Find matching messages in an Outlook / Microsoft 365 mailbox through Microsoft Graph."""
    from .connectors.outlook import GRAPH

    query = urllib.parse.urlencode({
        "$filter": f"receivedDateTime ge {since.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ} and hasAttachments eq true",
        "$orderby": "receivedDateTime desc", "$top": 50,
        "$select": "id,subject,from,receivedDateTime,internetMessageId",
    })
    url: str | None = f"{GRAPH}/me/messages?{query}"
    found: list[Found] = []
    while url and len(found) < MAX_PER_RUN:
        page = request(url, token=token)
        for m in page.get("value", []):
            msg_id = m.get("internetMessageId") or m["id"]
            if msg_id in seen:
                continue
            sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "")
            subject = m.get("subject") or ""
            atts = request(f"{GRAPH}/me/messages/{m['id']}/attachments", token=token).get("value", [])
            files = [(a["name"], base64.b64decode(a["contentBytes"])) for a in atts
                     if a.get("@odata.type") == "#microsoft.graph.fileAttachment" and not a.get("isInline")
                     and a.get("contentBytes") and wanted(a.get("name", ""), int(a.get("size", 0)), extensions)]
            rule = first_match(rules, inbox, sender, subject, [f for f, _ in files]) if files else None
            if rule is None:
                seen.add(msg_id)
                continue
            received = datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")).astimezone(tz)
            found.append(Found(inbox, msg_id, sender, subject, received, files, rule.name))
        url = page.get("@odata.nextLink")
    return found


# -- run -------------------------------------------------------------------------------------------

def scan(config: Config, settings: dict, days: int | None = None) -> tuple[list[Found], dict[str, list[str]], list[str]]:
    """Return ``(found, seen, errors)`` across every configured inbox."""
    rules = load_rules(settings)
    extensions = [e.lower().lstrip(".") for e in settings.get("extensions", DEFAULT_EXTENSIONS)]
    seen_all = load_seen()
    since = datetime.now(timezone.utc) - timedelta(days=int(days or settings.get("days", 365)))
    found: list[Found] = []
    errors: list[str] = []
    for options in config.connectors:
        if options.get("type") not in ("imap", "outlook"):
            continue
        name = options.get("name", options["type"])
        seen = set(seen_all.get(name, []))
        try:
            connector = build_connector(options, config)
            if options["type"] == "imap":
                with imaplib.IMAP4_SSL(options["host"], int(options.get("port", 993)), timeout=60,
                                       ssl_context=tls.context()) as conn:
                    found += imap_scan(conn, options, connector.secret("password"), rules, seen, since,
                                       extensions, config.tz)
            else:
                from .connectors.outlook import _request
                found += graph_scan(_request, connector.access_token(), name, rules, seen, since, extensions,
                                    config.tz)
        except (ConnectorError, imaplib.IMAP4.error, OSError, KeyError) as exc:
            errors.append(f"{name}: {exc}")
        seen_all[name] = sorted(seen)
    return found, seen_all, errors


def ingest(vault: Path) -> int:
    """Run the Second Brain's ingest on the vault inbox (the sibling project)."""
    sibling = PROJECT_DIR.parent / "02-second-brain"
    return subprocess.run([sys.executable, "-m", "second_brain", "ingest", "--vault", str(vault)], cwd=sibling).returncode


def load_settings(path: Path = RULES_FILE) -> dict:
    import tomllib

    if not path.is_file():
        return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def run(config: Config, days: int | None = None, dry_run: bool = False, do_ingest: bool = True,
        rules_file: Path = RULES_FILE) -> int:
    settings = load_settings(rules_file)
    if not settings.get("rules"):
        print(f"No rules in {rules_file} yet; nothing to import.")
        return 0
    if config.vault_path is None:
        print("No Second Brain vault (set VAULT_PATH in .env).", file=sys.stderr)
        return 1
    found, seen, errors = scan(config, settings, days)
    for e in errors:
        print(f"✘ {e}", file=sys.stderr)
    inbox = config.vault_path / "00 Inbox"
    saved = 0
    for f in found:
        names = ", ".join(n for n, _ in f.files)
        if dry_run:
            print(f"[{f.rule}] {f.received:%Y-%m-%d} {f.inbox} | {f.sender} | {f.subject} -> {names}")
            continue
        saved += len(save(f, inbox))
        seen.setdefault(f.inbox, []).append(f.message_id)
    if dry_run:
        print(f"{len(found)} emails would be imported (dry run: nothing saved).")
        return 0
    save_seen(seen)
    print(f"Saved {saved} attachment(s) from {len(found)} email(s) to {inbox}.")
    if saved and do_ingest:
        return ingest(config.vault_path)
    return 1 if errors and not found else 0
