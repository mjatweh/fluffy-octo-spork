"""Upcoming important dates (renewals, expiries, deadlines) from note frontmatter."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .vault import iter_notes, read_meta

# *_date keys that are history, not deadlines
IGNORED = {"start_date", "signed_date", "document_date", "created_date", "ingested_date"}
EXTRA_KEYS = {"due", "deadline", "renewal", "expiry", "expires"}


def _as_date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def upcoming(vault: Path, days: int = 30, today: dt.date | None = None, include_overdue: bool = False) -> list[dict]:
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=days)
    out = []
    for p in iter_notes(Path(vault)):
        meta, _ = read_meta(p)
        for key, val in meta.items():
            if not ((key.endswith("_date") and key not in IGNORED) or key in EXTRA_KEYS):
                continue
            d = _as_date(val)
            if d is None or d > horizon or (d < today and not include_overdue):
                continue
            out.append({
                "date": d.isoformat(),
                "days_left": (d - today).days,
                "label": key.removesuffix("_date").replace("_", " "),
                "note": str(p.relative_to(vault)),
                "name": p.stem,
                "title": str(meta.get("title") or p.stem),
                "type": meta.get("type"),
            })
    return sorted(out, key=lambda r: (r["date"], r["note"], r["label"]))


def format_table(rows: list[dict]) -> str:
    if not rows:
        return "No upcoming dates."
    return "\n".join(
        f"{r['date']}  {('in ' + str(r['days_left']) + 'd') if r['days_left'] >= 0 else str(-r['days_left']) + 'd ago':>9}"
        f"  {r['label']:<16} [[{r['name']}]]" for r in rows)
