"""Connect AI agents to the vault.

Three layers over the same five operations:
  1. Plain Python:   search(), read_note(), write_note(), upcoming_dates(), list_notes()
  2. Claude tools:   TOOLS (JSON schemas for `tools=`) + dispatch(name, input) / handle_tool_uses(content)
  3. MCP server:     `python -m second_brain mcp` (see mcp_server.py)

Every function takes an optional `vault`; default is $SECOND_BRAIN_VAULT, then $VAULT_PATH, then ./vault.

    from second_brain import agent_api
    resp = client.messages.create(model=..., tools=agent_api.TOOLS, messages=msgs, max_tokens=16000)
    msgs += [{"role": "assistant", "content": resp.content},
             {"role": "user", "content": agent_api.handle_tool_uses(resp.content)}]
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import config, index, reminders
from .vault import iter_notes, read_meta, resolve


def _v(vault) -> Path:
    return config.vault_path(vault)


def search(query: str, k: int = 5, vault=None) -> list[dict]:
    """BM25 search. Returns [{path, name, title, score, snippet}] best first."""
    return index.search(_v(vault), query, int(k))


def read_note(path: str, vault=None) -> dict:
    """Read a note by vault-relative path ('.md' optional). Returns {path, frontmatter, content}."""
    v = _v(vault)
    p = resolve(v, path, must_be_md=True)
    if not p.is_file():
        hits = [n for n in iter_notes(v) if n.stem.lower() == Path(path).stem.lower()]  # allow bare note names
        if not hits:
            raise FileNotFoundError(f"note not found: {path}")
        p = hits[0]
    meta, _ = read_meta(p)
    return {"path": str(p.relative_to(v)), "frontmatter": meta, "content": p.read_text(encoding="utf-8")}


def write_note(path: str, content: str, mode: str = "overwrite", vault=None) -> dict:
    """Create/overwrite/append a markdown note (vault-relative path; '.md' added if missing).

    mode: "overwrite" | "append" | "create" (fails if the note exists).
    """
    if mode not in ("overwrite", "append", "create"):
        raise ValueError("mode must be overwrite, append or create")
    v = _v(vault)
    p = resolve(v, path, must_be_md=True)
    if mode == "create" and p.exists():
        raise FileExistsError(f"note exists: {p.relative_to(v)}")
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and p.exists():
        existing = p.read_text(encoding="utf-8")
        content = existing + ("" if existing.endswith("\n") else "\n") + content
    p.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    return {"path": str(p.relative_to(v)), "bytes": p.stat().st_size, "mode": mode}


def upcoming_dates(days: int = 30, include_overdue: bool = False, vault=None, today: dt.date | None = None) -> list[dict]:
    """Renewals/expiries/deadlines within `days` from frontmatter *_date fields."""
    return reminders.upcoming(_v(vault), int(days), today=today, include_overdue=include_overdue)


def list_notes(folder: str = "", vault=None) -> list[dict]:
    """List notes (optionally under a folder) with title and type."""
    v = _v(vault)
    base = resolve(v, folder) if folder else v
    out = []
    for p in iter_notes(v):
        if base == v or base in p.parents:
            meta, _ = read_meta(p)
            out.append({"path": str(p.relative_to(v)), "title": meta.get("title") or p.stem, "type": meta.get("type")})
    return out


# ---- Claude tool definitions -------------------------------------------------------------
TOOLS: list[dict] = [
    {
        "name": "vault_search",
        "description": "Full-text search the user's Obsidian second brain (contracts, leases, insurance, "
                       "finance, notes, daily/weekly notes). Returns best-matching notes with snippets. "
                       "Use before answering questions about the user's documents.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Keywords, e.g. 'lease renewal notice'"},
            "k": {"type": "integer", "description": "Max results (default 5)", "minimum": 1, "maximum": 25}},
            "required": ["query"], "additionalProperties": False},
    },
    {
        "name": "vault_read_note",
        "description": "Read a vault note's full markdown and parsed frontmatter. Accepts a vault-relative "
                       "path from vault_search/vault_list_notes (e.g. 'Life Admin/Housing/Lease.md') or a bare note name.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}},
                         "required": ["path"], "additionalProperties": False},
    },
    {
        "name": "vault_write_note",
        "description": "Create, overwrite or append to a markdown note in the vault. Agents should write to "
                       "their own folders: 'Daily/YYYY-MM-DD.md', 'Weekly/YYYY-Www.md', 'Content/...', "
                       "'Agents/<agent-name>/...'. Use [[wikilinks]] to reference other notes.",
        "input_schema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Vault-relative path; .md is added if missing"},
            "content": {"type": "string", "description": "Markdown, optionally with YAML frontmatter"},
            "mode": {"type": "string", "enum": ["overwrite", "append", "create"], "description": "Default overwrite"}},
            "required": ["path", "content"], "additionalProperties": False},
    },
    {
        "name": "vault_upcoming_dates",
        "description": "List upcoming renewals, expiries, notice deadlines and due dates found in the vault, "
                       "soonest first.",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Look-ahead window in days (default 30)", "minimum": 0},
            "include_overdue": {"type": "boolean", "description": "Also include past dates (default false)"}},
            "required": [], "additionalProperties": False},
    },
    {
        "name": "vault_list_notes",
        "description": "List notes in the vault or a folder (e.g. 'Business/Contracts') with titles and types.",
        "input_schema": {"type": "object", "properties": {"folder": {"type": "string"}},
                         "required": [], "additionalProperties": False},
    },
]
_FUNCS = {"vault_search": search, "vault_read_note": read_note, "vault_write_note": write_note,
          "vault_upcoming_dates": upcoming_dates, "vault_list_notes": list_notes}
TOOL_NAMES = list(_FUNCS)


def dispatch(name: str, tool_input: dict | None, vault=None) -> str:
    """Run one tool call; returns a JSON string. Raises KeyError for unknown tools."""
    if name not in _FUNCS:
        raise KeyError(f"unknown tool: {name}")
    args = dict(tool_input or {})
    schema = next(t["input_schema"] for t in TOOLS if t["name"] == name)
    missing = [r for r in schema["required"] if r not in args]
    extra = [a for a in args if a not in schema["properties"]]
    if missing or extra:
        raise ValueError(f"{name}: missing {missing}, unexpected {extra}")
    return json.dumps(_FUNCS[name](**args, vault=vault), ensure_ascii=False, default=str)


def handle_tool_uses(content, vault=None) -> list[dict]:
    """Turn an assistant message's tool_use blocks into tool_result blocks (one user message)."""
    results = []
    for block in content:
        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if btype != "tool_use":
            continue
        get = (lambda k: block[k]) if isinstance(block, dict) else (lambda k: getattr(block, k))
        try:
            results.append({"type": "tool_result", "tool_use_id": get("id"), "content": dispatch(get("name"), get("input"), vault)})
        except Exception as e:
            results.append({"type": "tool_result", "tool_use_id": get("id"), "content": f"Error: {e}", "is_error": True})
    return results
