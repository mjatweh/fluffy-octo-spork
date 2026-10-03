"""collect → normalize → brief → render."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .briefing import generate_briefing
from .config import Config
from .connectors import build_connector
from .models import DayData, Email, Event, SourceStatus, Task
from .normalize import normalize_emails, normalize_events, normalize_tasks, tag_emails
from .render import render_html, render_markdown, write_vault_note

log = logging.getLogger(__name__)


def collect(config: Config, day: date) -> DayData:
    data = DayData(day=day, generated_at=datetime.now(config.tz), links=list(config.links))
    events: list[Event] = []
    emails: list[Email] = []
    tasks: list[Task] = []
    buckets = {"calendar": events, "email": emails, "tasks": tasks}
    for options in config.connectors:
        t0 = time.perf_counter()
        name, ctype, kind = options.get("name") or options.get("type", "?"), options.get("type", "?"), "?"
        try:
            connector = build_connector(options, config)
            kind = connector.kind
            items = connector.fetch(day)
            if kind == "email":
                tag_emails(items, options, name)
            buckets[kind].extend(items)
            status = SourceStatus(name, ctype, kind, ok=True, count=len(items))
        except Exception as exc:  # one broken source must not break the dashboard
            log.warning("connector %s failed: %s", name, exc)
            status = SourceStatus(name, ctype, kind, ok=False, message=str(exc) or type(exc).__name__)
        status.elapsed_ms = int((time.perf_counter() - t0) * 1000)
        data.statuses.append(status)

    data.events = normalize_events(events)
    data.emails = normalize_emails(emails, config.max_emails)
    data.tasks = normalize_tasks(tasks, day)
    return data


@dataclass
class BuildResult:
    html: Path
    markdown: Path
    vault_note: Path | None
    note: str
    data: DayData
    briefing: Any


def build(config: Config, day: date | None = None, offline: bool = False, client: Any = None) -> BuildResult:
    day = day or datetime.now(config.tz).date()
    data = collect(config, day)
    briefing, note = generate_briefing(data, config.model, offline=offline, client=client)

    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(data, briefing)
    html_path = out / "dashboard.html"
    html_path.write_text(render_html(data, briefing, note), encoding="utf-8")
    md_path = out / f"briefing-{day.isoformat()}.md"
    md_path.write_text(markdown, encoding="utf-8")
    (out / "briefing.md").write_text(markdown, encoding="utf-8")

    vault_note = write_vault_note(config.vault_path, data, markdown) if config.vault_path else None
    return BuildResult(html_path, md_path, vault_note, note, data, briefing)
