"""Normalized data model shared by connectors, the briefing step and the renderer."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    location: str = ""
    description: str = ""
    source: str = ""
    conflict: bool = False

    @property
    def join_url(self) -> str:
        """Online-meeting link (Teams/Zoom) when the description is just an https URL."""
        d = self.description.strip()
        return d if d.startswith("https://") and " " not in d and "\n" not in d else ""

    @property
    def time_label(self) -> str:
        if self.all_day:
            return "All day"
        return f"{self.start:%H:%M}–{self.end:%H:%M}"

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class Email:
    sender: str
    subject: str
    received: datetime
    snippet: str = ""
    unread: bool = True
    flagged: bool = False
    needs_reply: bool = False
    source: str = ""


PRIORITY_LABELS = {1: "urgent", 2: "high", 3: "normal", 4: "low"}


@dataclass
class Task:
    title: str
    due: date | None = None
    priority: int = 3  # 1 = urgent ... 4 = low
    done: bool = False
    project: str = ""
    source: str = ""
    overdue: bool = False
    due_today: bool = False

    @property
    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, "normal")


@dataclass
class SourceStatus:
    name: str
    type: str
    kind: str
    ok: bool
    count: int = 0
    message: str = ""
    elapsed_ms: int = 0


@dataclass
class Briefing:
    headline: str
    summary: str
    top_priorities: list[str] = field(default_factory=list)
    schedule_highlights: list[str] = field(default_factory=list)
    emails_to_reply: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    focus_tip: str = ""
    generated_by: str = "template"  # "template" or the model id

    @classmethod
    def from_dict(cls, data: dict[str, Any], generated_by: str) -> "Briefing":
        keys = cls.__dataclass_fields__.keys() - {"generated_by"}
        return cls(**{k: data[k] for k in keys if k in data}, generated_by=generated_by)


@dataclass
class DayData:
    day: date
    generated_at: datetime
    events: list[Event] = field(default_factory=list)
    emails: list[Email] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    statuses: list[SourceStatus] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)

    @property
    def conflicts(self) -> list[Event]:
        return [e for e in self.events if e.conflict]

    @property
    def needs_reply(self) -> list[Email]:
        return [e for e in self.emails if e.needs_reply]

    def to_prompt_dict(self) -> dict[str, Any]:
        """Compact, JSON-serializable view handed to the LLM."""

        def clean(obj: Any) -> Any:
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: clean(v) for k, v in obj.items() if v not in ("", None)}
            if isinstance(obj, list):
                return [clean(v) for v in obj]
            return obj

        return clean(
            {
                "date": self.day,
                "weekday": f"{self.day:%A}",
                "events": [asdict(e) for e in self.events],
                "emails": [asdict(e) for e in self.emails],
                "tasks": [asdict(t) for t in self.tasks if not t.done],
                "unavailable_sources": [s.name for s in self.statuses if not s.ok],
            }
        )
