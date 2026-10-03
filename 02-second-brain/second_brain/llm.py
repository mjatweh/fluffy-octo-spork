"""Claude calls (structured metadata extraction + grounded Q&A).

Every function takes an explicit `client` so tests can pass a mock; callers fall
back to heuristics whenever this module returns None.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys

from . import config
from .classify import CATEGORIES, CATEGORY_NAMES, OTHER

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_DOC_CHARS = 400_000  # ~100k tokens; longer docs are truncated with a warning

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Short human title, e.g. 'Apartment Lease - 12 Oak St'"},
        "category": {"type": "string", "enum": CATEGORY_NAMES},
        "doc_type": {"type": "string", "description": "kebab-case type, e.g. lease-agreement, auto-insurance, nda, invoice"},
        "summary": {"type": "string", "description": "2-4 sentence plain-English summary of what matters"},
        "parties": {"type": "array", "items": {"type": "string"}},
        "dates": {
            "type": "array",
            "description": "Important dates. label examples: renewal, expiry, start, due, signed, notice_deadline",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"}},
                "required": ["label", "date"],
                "additionalProperties": False,
            },
        },
        "amounts": {"type": "array", "items": {"type": "string"}, "description": "e.g. '$2,400/month rent'"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "category", "doc_type", "summary", "parties", "dates", "amounts", "tags"],
    "additionalProperties": False,
}

EXTRACT_SYSTEM = (
    "You file personal and business admin documents into an Obsidian second brain. "
    "Extract metadata faithfully from the document; never invent parties, dates or amounts. "
    "Categories: lease (housing/rent/mortgage), insurance, contract (business agreements), client "
    "(proposals, client material), finance (invoices, receipts, tax, bank), health, vehicle, note "
    "(personal notes/meetings), other. Include notice deadlines when a notice period is stated."
)
ANSWER_SYSTEM = (
    "You answer questions using ONLY the user's vault notes provided. Cite every fact with the note "
    "name as an Obsidian wikilink, e.g. [[Apartment Lease]]. If the notes don't contain the answer, say so."
)


def get_client():
    import anthropic

    return anthropic.Anthropic()


def _warn(msg: str) -> None:
    print(f"[second-brain] {msg}", file=sys.stderr)


def _create(client, **params):
    params = {"model": config.model(), "max_tokens": 16000, **params}
    if config.use_fallbacks():
        return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
    return client.messages.create(**params)


def _call(client, **params) -> str | None:
    import anthropic

    try:
        resp = _create(client, **params)
    except anthropic.RateLimitError as e:
        _warn(f"rate limited, using offline fallback ({e})")
        return None
    except anthropic.APIStatusError as e:
        _warn(f"API error {e.status_code}, using offline fallback: {e.message}")
        return None
    except anthropic.APIConnectionError as e:
        _warn(f"connection error, using offline fallback ({e})")
        return None
    if getattr(resp, "stop_reason", None) == "refusal":
        _warn("request declined by Claude; using offline fallback")
        return None
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return text or None


def extract_metadata(text: str, filename: str, client) -> dict | None:
    if len(text) > MAX_DOC_CHARS:
        _warn(f"{filename}: {len(text):,} chars, sending first {MAX_DOC_CHARS:,} to Claude")
        text = text[:MAX_DOC_CHARS]
    out = _call(
        client,
        system=EXTRACT_SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": EXTRACT_SCHEMA}},
        messages=[{"role": "user", "content": f"Filename: {filename}\n\n<document>\n{text}\n</document>"}],
    )
    if not out:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        _warn("could not parse Claude's JSON; using offline fallback")
        return None
    return normalize(data)


def normalize(data: dict) -> dict:
    """Coerce Claude's output into the same shape as classify.heuristic_metadata."""
    cat = data.get("category") if data.get("category") in CATEGORIES else OTHER[0]
    dates: dict[str, str] = {}
    for item in data.get("dates") or []:
        label = re.sub(r"[^a-z0-9]+", "_", str(item.get("label", "")).lower()).strip("_") or "important"
        label = label if label.endswith("_date") else label + "_date"
        try:
            dates.setdefault(label, dt.date.fromisoformat(str(item.get("date", ""))[:10]).isoformat())
        except ValueError:
            continue
    tags = [re.sub(r"[^\w/-]+", "-", t.strip().lower()).strip("-") for t in data.get("tags") or []]
    return {
        "title": str(data.get("title") or "").strip(),
        "category": cat,
        "folder": CATEGORIES[cat][0] if cat in CATEGORIES else OTHER[1],
        "doc_type": str(data.get("doc_type") or cat),
        "summary": str(data.get("summary") or "").strip(),
        "parties": [str(p).strip() for p in data.get("parties") or [] if str(p).strip()],
        "dates": dates,
        "amounts": [str(a) for a in data.get("amounts") or []],
        "tags": [t for t in tags if t],
    }


def answer(question: str, notes: list[tuple[str, str]], client) -> str | None:
    """notes: [(note_name, content)]."""
    docs = "\n\n".join(f'<note name="{n}">\n{c}\n</note>' for n, c in notes)
    return _call(
        client,
        system=ANSWER_SYSTEM,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": f"{docs}\n\nQuestion: {question}"}],
    )
