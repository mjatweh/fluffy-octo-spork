"""Todoist connector (HTTP, stdlib ``urllib``). Optional — needs an API token
from Todoist Settings → Integrations → Developer."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date

from ..models import Task
from .base import Connector, register

# Todoist priorities: 4 = urgent (red) ... 1 = normal. Ours: 1 = urgent ... 4 = low.
PRIORITY_MAP = {4: 1, 3: 2, 2: 3, 1: 3}


def parse_tasks(payload, source: str = "") -> list[Task]:
    items = payload.get("results", []) if isinstance(payload, dict) else payload
    out = []
    for item in items:
        due = (item.get("due") or {}).get("date")
        out.append(
            Task(
                title=item.get("content", ""),
                due=date.fromisoformat(due[:10]) if due else None,
                priority=PRIORITY_MAP.get(item.get("priority", 1), 3),
                project=str(item.get("project_name") or ""),
                source=source,
            )
        )
    return out


@register
class Todoist(Connector):
    """``type = "todoist"`` — options: ``token_env`` (e.g. TODOIST_API_TOKEN),
    ``filter`` (default ``today | overdue``), ``api_url``."""

    type = "todoist"
    kind = "tasks"

    def fetch(self, day: date) -> list[Task]:
        token = self.secret("token")
        base = self.option("api_url", "https://api.todoist.com/api/v1/tasks/filter")
        url = f"{base}?{urllib.parse.urlencode({'query': self.option('filter', 'today | overdue')})}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return parse_tasks(json.load(resp), self.name)
