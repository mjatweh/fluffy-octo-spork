"""`ask`: retrieve top notes, then answer with Claude (or return snippets offline)."""
from __future__ import annotations

import re
from pathlib import Path

from . import config, llm
from .index import search
from .vault import read_meta

NOTE_CHARS = 30_000
DATE_HINTS = {"renew": "renewal_date", "expir": "expiry_date", "end": "expiry_date", "due": "due_date",
              "notice": "notice_deadline_date", "cancel": "notice_deadline_date", "start": "start_date"}


def _offline(vault: Path, question: str, hits: list[dict]) -> str:
    if not hits:
        return "No matching notes found."
    lines = []
    q = question.lower()
    meta, _ = read_meta(vault / hits[0]["path"])
    for hint, key in DATE_HINTS.items():
        if re.search(r"\b" + hint, q) and meta.get(key):
            lines.append(f"Likely answer: {key.removesuffix('_date').replace('_', ' ')} = {meta[key]} "
                         f"(from [[{hits[0]['name']}]])\n")
            break
    lines.append("Top matching notes (offline mode):")
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. [[{h['name']}]] (score {h['score']})\n   {h['snippet']}")
    return "\n".join(lines)


def ask(vault: Path, question: str, k: int = 5, dry_run: bool = False, client=None) -> str:
    vault = Path(vault)
    hits = search(vault, question, k)
    if client is None and not dry_run and config.has_api_key():
        client = llm.get_client()
    if client is None or not hits:
        return _offline(vault, question, hits)
    notes = []
    for h in hits:
        text = (vault / h["path"]).read_text(encoding="utf-8", errors="replace")
        if len(text) > NOTE_CHARS:
            llm._warn(f"{h['name']}: truncated to {NOTE_CHARS:,} chars for the prompt")
            text = text[:NOTE_CHARS]
        notes.append((h["name"], text))
    return llm.answer(question, notes, client) or _offline(vault, question, hits)
