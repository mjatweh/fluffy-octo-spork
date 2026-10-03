"""Obsidian vault integration: upsert our own marked sections, never clobber others."""
from __future__ import annotations

import re
from pathlib import Path

MARK = "exec-assistant"


def _markers(section: str) -> tuple[str, str]:
    return f"<!-- {MARK}:{section}:start -->", f"<!-- {MARK}:{section}:end -->"


def upsert_section(path: Path, section: str, body: str, title: str | None = None,
                   before: str | None = None) -> Path:
    """Insert or replace the block delimited by our markers for ``section``.

    Content outside our markers (e.g. a Life Dashboard briefing) is preserved byte-for-byte.
    If ``before`` names another of our sections already in the file, a new block is
    inserted ahead of it (keeps "Morning" above "Evening").
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    start, end = _markers(section)
    block = f"{start}\n{body.strip()}\n{end}"
    text = path.read_text() if path.exists() else (f"# {title}\n" if title else "")
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if pattern.search(text):
        text = pattern.sub(lambda _: block, text, count=1)
    elif before and _markers(before)[0] in text:
        anchor = _markers(before)[0]
        text = text.replace(anchor, f"{block}\n\n{anchor}", 1)
    else:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + block + "\n"
    path.write_text(text)
    return path


def daily_note(vault: Path, day: str) -> Path:
    return vault / "Daily" / f"{day}.md"


def weekly_note(vault: Path, week: str) -> Path:
    return vault / "Weekly" / f"{week}.md"


def write_morning(vault: Path, day: str, body: str) -> Path:
    return upsert_section(daily_note(vault, day), "morning", "## Morning check-in\n\n" + body,
                          title=day, before="evening")


def write_evening(vault: Path, day: str, body: str) -> Path:
    return upsert_section(daily_note(vault, day), "evening", "## Evening review\n\n" + body, title=day)


def write_weekly(vault: Path, week: str, body: str) -> Path:
    return upsert_section(weekly_note(vault, week), "weekly", body, title=week)
