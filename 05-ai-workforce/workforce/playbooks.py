"""Playbooks: reusable goal templates in playbooks/<name>.toml with {var} placeholders."""
from __future__ import annotations

import tomllib
from pathlib import Path


def list_playbooks(directory: Path) -> dict[str, dict]:
    return {p.stem: tomllib.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.toml"))}


def render_playbook(directory: Path, name: str, overrides: dict[str, str] | None = None) -> tuple[str, str]:
    """Return (title, goal) with defaults from [vars] overridden by --var key=value."""
    books = list_playbooks(directory)
    if name not in books:
        raise KeyError(f"unknown playbook {name!r}; available: {', '.join(books) or 'none'}")
    book = books[name]
    values = {**book.get("vars", {}), **(overrides or {})}
    try:
        goal = book["goal"].strip().format(**values)
    except KeyError as e:
        raise KeyError(f"playbook {name!r} needs --var {e.args[0]}=...") from None
    return book.get("title", name), goal
