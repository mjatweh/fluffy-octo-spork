"""Local task list connector: a JSON file or a Markdown checklist.

Markdown lines look like (Obsidian Tasks emoji syntax is understood too)::

    - [ ] Send invoice to ACME due:2026-10-03 !high #work
    - [ ] Renew passport 📅 2026-10-10 ⏫
    - [x] Done things are skipped

JSON is a list of objects: ``{"title", "due" (YYYY-MM-DD), "priority" (1-4 or
"urgent"/"high"/"normal"/"low"), "done", "project"}``.
"""
from __future__ import annotations

import json
import re
from datetime import date

from ..models import Task
from .base import Connector, register

PRIORITY_WORDS = {"urgent": 1, "p1": 1, "high": 2, "p2": 2, "normal": 3, "medium": 3, "med": 3, "p3": 3, "low": 4, "p4": 4}
EMOJI_PRIORITY = {"🔺": 1, "⏫": 2, "🔼": 2, "🔽": 4, "⏬": 4}
CHECKBOX = re.compile(r"^\s*[-*+]\s+\[(?P<mark>[ xX/-])\]\s+(?P<body>.+)$")
DUE = re.compile(r"(?:due:|📅\s*)(\d{4}-\d{2}-\d{2})")
BANG = re.compile(r"(?<!\S)!(urgent|high|normal|medium|med|low|p[1-4])\b", re.I)
TAG = re.compile(r"(?<!\S)#([\w/-]+)")


def _priority(value) -> int:
    if isinstance(value, int):
        return min(max(value, 1), 4)
    return PRIORITY_WORDS.get(str(value).lower(), 3)


def parse_markdown(text: str, source: str = "") -> list[Task]:
    tasks = []
    for line in text.splitlines():
        m = CHECKBOX.match(line)
        if not m:
            continue
        body = m.group("body")
        due = DUE.search(body)
        bang = BANG.search(body)
        prio = _priority(bang.group(1)) if bang else next((p for e, p in EMOJI_PRIORITY.items() if e in body), 3)
        tag = TAG.search(body)
        title = BANG.sub("", DUE.sub("", body))
        title = re.sub(r"[🔺⏫🔼🔽⏬]", "", TAG.sub("", title))
        tasks.append(
            Task(
                title=re.sub(r"\s+", " ", title).strip(),
                due=date.fromisoformat(due.group(1)) if due else None,
                priority=prio,
                done=m.group("mark") in "xX-",
                project=tag.group(1) if tag else "",
                source=source,
            )
        )
    return tasks


def parse_json(text: str, source: str = "") -> list[Task]:
    data = json.loads(text)
    items = data.get("tasks", []) if isinstance(data, dict) else data
    return [
        Task(
            title=i["title"],
            due=date.fromisoformat(i["due"]) if i.get("due") else None,
            priority=_priority(i.get("priority", 3)),
            done=bool(i.get("done", False)),
            project=i.get("project", ""),
            source=source,
        )
        for i in items
    ]


@register
class TasksFile(Connector):
    """``type = "tasks_file"`` — options: ``path`` (.json or .md)."""

    type = "tasks_file"
    kind = "tasks"

    def fetch(self, day: date) -> list[Task]:
        path = self.option("path", required=True)
        text = self.read_text(path)
        parser = parse_json if str(path).lower().endswith(".json") else parse_markdown
        return [t for t in parser(text, self.name) if not t.done]
