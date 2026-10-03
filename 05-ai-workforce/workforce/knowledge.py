"""Second Brain adapter.

Prefers the sibling project's `second_brain.agent_api` (../02-second-brain, imported lazily at call time so
it is never a hard dependency). Falls back to a plain markdown folder: $VAULT_PATH, else <workspace>/knowledge.
"""
from __future__ import annotations

import datetime as dt
import importlib
import inspect
import re
import sys
import threading
from pathlib import Path
from typing import Any

from .safety import safe_path

DATE_RE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")


class SecondBrain:
    def __init__(self, sibling_dir: Path | None, notes_dir: Path, use_sibling: bool = True,
                 vault: str | None = None):
        self.sibling_dir = sibling_dir
        self.vault = vault  # passed to the sibling API's `vault=` parameter when set
        self.notes_dir = notes_dir
        self.use_sibling = use_sibling
        self._api: Any = None
        self._tried = False
        self._lock = threading.Lock()  # parallel agents may hit the first import at the same time

    @property
    def api(self) -> Any:
        """The sibling agent_api module, or None (cached after the first attempt)."""
        with self._lock:
            if self._tried:
                return self._api
            self._tried = True
            if self.use_sibling and self.sibling_dir and (self.sibling_dir / "second_brain").is_dir():
                if str(self.sibling_dir) not in sys.path:
                    sys.path.insert(0, str(self.sibling_dir))
                try:
                    self._api = importlib.import_module("second_brain.agent_api")
                except Exception:
                    self._api = None
        return self._api

    @property
    def backend(self) -> str:
        return "second_brain.agent_api" if self.api else f"local markdown ({self.notes_dir})"

    def _call(self, fn: str, *args: Any, **kwargs: Any) -> Any:
        """Call the sibling API, passing only keyword args its signature accepts (with aliases)."""
        f = getattr(self.api, fn)
        params = inspect.signature(f).parameters
        aliases = {"limit": ("limit", "k", "top_k", "n")}
        out = {}
        for key, val in kwargs.items():
            name = next((a for a in aliases.get(key, (key,)) if a in params), None)
            if name:
                out[name] = val
        if self.vault and "vault" in params:
            out["vault"] = self.vault
        return f(*args, **out)

    # --- operations -------------------------------------------------------------------------
    def search(self, query: str, limit: int = 5) -> Any:
        if self.api and hasattr(self.api, "search"):
            return self._call("search", query, limit=limit)
        terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 2]
        hits = []
        for p in sorted(self.notes_dir.rglob("*.md")) if self.notes_dir.is_dir() else []:
            text = p.read_text(encoding="utf-8", errors="ignore")
            low = (p.stem + " " + text).lower()
            score = sum(low.count(t) for t in terms)
            if score:
                i = min((low.find(t) for t in terms if t in low), default=0)
                snippet = " ".join(text[max(0, i - 80): i + 200].split())
                hits.append({"path": str(p.relative_to(self.notes_dir)), "title": p.stem,
                             "score": score, "snippet": snippet})
        hits.sort(key=lambda h: -h["score"])
        return hits[:limit] or f"No notes matched {query!r}."

    def read_note(self, path: str) -> str:
        if self.api and hasattr(self.api, "read_note"):
            return self._call("read_note", path)
        return safe_path(self.notes_dir, path).read_text(encoding="utf-8")

    def write_note(self, path: str, content: str) -> str:
        if self.api and hasattr(self.api, "write_note"):
            return str(self._call("write_note", path, content) or f"wrote {path}")
        if not path.endswith(".md"):
            path += ".md"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        full = safe_path(self.notes_dir, path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return f"wrote {full.relative_to(self.notes_dir.resolve())}"

    def upcoming_dates(self, days: int = 14) -> Any:
        if self.api and hasattr(self.api, "upcoming_dates"):
            return self._call("upcoming_dates", days=days)
        today, out = dt.date.today(), []
        for p in sorted(self.notes_dir.rglob("*.md")) if self.notes_dir.is_dir() else []:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                for d in DATE_RE.findall(line):
                    try:
                        when = dt.date.fromisoformat(d)
                    except ValueError:
                        continue
                    if 0 <= (when - today).days <= days:
                        out.append({"date": d, "note": p.stem, "line": line.strip()[:200]})
        return sorted(out, key=lambda x: x["date"]) or f"No dated items in the next {days} days."
