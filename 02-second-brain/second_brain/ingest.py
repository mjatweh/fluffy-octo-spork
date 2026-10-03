"""Drop folder -> Obsidian notes. Idempotent via the source file's SHA-256."""
from __future__ import annotations

import datetime as dt
import hashlib
import shutil
from pathlib import Path
from typing import Callable

from . import config, frontmatter, llm
from .classify import heuristic_metadata
from .extract import extract_text, kind
from .vault import iter_notes, read_meta, safe_name, unique_path

HUBS = {"lease": "Housing", "insurance": "Insurance", "contract": "Contracts", "client": "Clients",
        "finance": "Finance", "health": "Health", "vehicle": "Vehicles", "note": "Notes", "other": "Unsorted"}
EXCERPT_CHARS = 20_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _known(vault: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    """(source hash -> note path, party(lower) -> [note names]) from existing notes."""
    hashes, parties = {}, {}
    for p in iter_notes(vault):
        meta, _ = read_meta(p)
        if meta.get("source_sha256"):
            hashes[meta["source_sha256"]] = str(p.relative_to(vault))
        for party in meta.get("parties") or []:
            parties.setdefault(str(party).lower(), []).append(p.stem)
    return hashes, parties


def _inbox_files(inbox: Path, vault: Path) -> list[Path]:
    out = []
    for p in sorted(inbox.rglob("*")):
        rel = p.relative_to(inbox).parts
        if not p.is_file() or any(x.startswith(".") for x in rel):
            continue
        if p.suffix.lower() == ".md":  # never re-ingest our own notes
            meta, _ = read_meta(p)
            if meta.get("generated_by") == config.GENERATED_BY:
                continue
        out.append(p)
    return out


def _wikilink(name: str) -> str:
    return f"[[{safe_name(name)}]]"


def render_note(meta: dict, attachment: str, text: str, src_hash: str, extracted_by: str,
                related: list[str], warning: str | None) -> str:
    fm = {
        "title": meta["title"],
        "type": meta["doc_type"],
        "category": meta["category"],
        "tags": sorted(set(meta["tags"]), key=meta["tags"].index),
        "parties": meta["parties"],
        **dict(sorted(meta["dates"].items())),
        "notice_days": meta.get("notice_days"),
        "amounts": meta["amounts"],
        "source_file": f"[[{attachment}]]",
        "source_sha256": src_hash,
        "ingested": dt.date.today().isoformat(),
        "extracted_by": extracted_by,
        "generated_by": config.GENERATED_BY,
    }
    lines = [f"# {meta['title']}", "", "> [!summary]", f"> {meta['summary']}", "", "## Key details",
             f"- **Type:** {meta['doc_type']}"]
    if meta["parties"]:
        lines.append("- **Parties:** " + ", ".join(_wikilink(p) for p in meta["parties"]))
    for k, v in sorted(meta["dates"].items()):
        lines.append(f"- **{k.removesuffix('_date').replace('_', ' ').capitalize()}:** {v}")
    if meta.get("notice_days"):
        lines.append(f"- **Notice period:** {meta['notice_days']} days")
    if meta["amounts"]:
        lines.append("- **Amounts:** " + ", ".join(meta["amounts"]))
    lines += ["", "## Source", f"![[{attachment}]]"]
    if warning:
        lines.append(f"\n> [!warning] {warning}")
    lines += ["", "## Related", f"- [[{HUBS.get(meta['category'], 'Unsorted')}]] · [[Home]]"]
    lines += [f"- [[{r}]]" for r in related]
    if text.strip():
        excerpt = text.strip()[:EXCERPT_CHARS]
        lines += ["", "## Extracted text", "> [!quote]- Full text" + (" (truncated)" if len(text.strip()) > EXCERPT_CHARS else "")]
        lines += [f"> {ln}".rstrip() for ln in excerpt.splitlines()]
    return frontmatter.render(fm, "\n".join(lines) + "\n")


def ingest(inbox: Path, vault: Path, *, dry_run: bool = False, client=None, move: bool | None = None,
           log: Callable[[str], None] = print) -> list[dict]:
    """Ingest every file in `inbox` into `vault`.

    dry_run: never call Claude (deterministic heuristics). Auto-enabled when no API key.
    move: delete the original after ingest (default: True only when the inbox is inside the vault).
    """
    inbox, vault = Path(inbox).resolve(), Path(vault).resolve()
    if not inbox.is_dir():
        raise FileNotFoundError(f"inbox not found: {inbox}")
    if move is None:
        move = vault in inbox.parents or inbox == vault
    if client is None and not dry_run and config.has_api_key():
        client = llm.get_client()
    if client is None and not dry_run:
        log("No ANTHROPIC_API_KEY: using offline heuristics.")
    hashes, party_index = _known(vault)
    (vault / "Attachments").mkdir(parents=True, exist_ok=True)
    results = []
    for src in _inbox_files(inbox, vault):
        rel_src = src.relative_to(inbox)
        h = sha256(src)
        if h in hashes:
            results.append({"file": str(rel_src), "status": "skipped", "note": hashes[h]})
            log(f"skip    {rel_src} (already ingested -> {hashes[h]})")
            if move:
                src.unlink()
            continue
        try:
            text, warning = extract_text(src)
            meta, extracted_by = heuristic_metadata(text, src.name), "heuristic"
            if client is not None and (text.strip() or kind(src) != "image"):
                ai = llm.extract_metadata(text or f"(no text could be extracted from {src.name})", src.name, client)
                if ai:
                    # Claude refines; heuristics fill anything it left empty.
                    meta = {**meta, **{k: v for k, v in ai.items() if v not in ("", [], {}, None)}}
                    extracted_by = "claude"
            meta["title"] = safe_name(meta["title"])
            att = vault / "Attachments" / src.name
            if att.exists():  # same name, different content
                att = att.with_name(f"{src.stem}-{h[:8]}{src.suffix}")
            shutil.copy2(src, att)
            folder = vault / meta["folder"]
            folder.mkdir(parents=True, exist_ok=True)
            note = unique_path(folder / f"{meta['title']}.md")
            related = sorted({n for p in meta["parties"] for n in party_index.get(p.lower(), []) if n != note.stem})
            note.write_text(render_note(meta, att.name, text, h, extracted_by, related, warning), encoding="utf-8")
            rel_note = str(note.relative_to(vault))
            hashes[h] = rel_note
            for p in meta["parties"]:
                party_index.setdefault(p.lower(), []).append(note.stem)
            if move:
                src.unlink()
            results.append({"file": str(rel_src), "status": "ingested", "note": rel_note,
                            "category": meta["category"], "extracted_by": extracted_by})
            log(f"ingest  {rel_src} -> {rel_note} [{meta['category']}, {extracted_by}]")
        except Exception as e:  # keep going; report per-file errors
            results.append({"file": str(rel_src), "status": "error", "error": str(e)})
            log(f"error   {rel_src}: {e}")
    if any(r["status"] == "ingested" for r in results):
        from .index import refresh

        refresh(vault)
    return results
