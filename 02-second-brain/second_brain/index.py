"""Local full-text search: pure-Python BM25 over vault notes, cached as JSON.

The index lives in <vault>/.second_brain/index.json and is refreshed
incrementally (by mtime) before every search, so agents never see stale results.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from . import config
from .vault import iter_notes, read_meta

VERSION = 2
K1, B = 1.5, 0.75
TITLE_WEIGHT = 3
STOP = set("""a an and are as at be by for from has have how i if in is it its me my of on or our so that the
this to was were what when where which who will with you your do does did can about into than then there
""".split())
_SUFFIXES = ("ations", "ation", "ings", "ing", "ies", "als", "al", "ers", "er", "es", "ed", "ly", "s")


def stem(w: str) -> str:
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)] + ("y" if suf == "ies" else "")
            break
    return w[:-1] if len(w) > 4 and w[-1] in "ey" else w


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1]


def _index_path(vault: Path) -> Path:
    return vault / config.STATE_DIR / "index.json"


def _doc_tokens(path: Path, vault: Path) -> tuple[str, list[str]]:
    meta, body = read_meta(path)
    title = str(meta.get("title") or path.stem)
    fm_text = " ".join(f"{k.replace('_', ' ')} {' '.join(map(str, v)) if isinstance(v, list) else v}"
                       for k, v in meta.items() if k not in ("source_sha256", "generated_by"))
    folder = " ".join(path.relative_to(vault).parts[:-1])
    toks = tokenize(f"{title} {path.stem} ") * TITLE_WEIGHT + tokenize(f"{folder} {fm_text} {body}")
    return title, toks


def load(vault: Path) -> dict:
    try:
        data = json.loads(_index_path(vault).read_text())
        if data.get("version") == VERSION:
            return data
    except (OSError, ValueError):
        pass
    return {"version": VERSION, "docs": {}}


def refresh(vault: Path, force: bool = False) -> dict:
    """Re-tokenize new/changed notes, drop deleted ones, persist. Returns the index."""
    vault = Path(vault)
    data = {"version": VERSION, "docs": {}} if force else load(vault)
    docs, seen, changed = data["docs"], set(), force
    for p in iter_notes(vault):
        rel = str(p.relative_to(vault))
        seen.add(rel)
        mtime = p.stat().st_mtime
        if rel in docs and docs[rel]["mtime"] == mtime:
            continue
        title, toks = _doc_tokens(p, vault)
        docs[rel] = {"mtime": mtime, "title": title, "len": len(toks), "tf": dict(Counter(toks))}
        changed = True
    for rel in set(docs) - seen:
        del docs[rel]
        changed = True
    if changed:
        ip = _index_path(vault)
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(json.dumps(data))
    return data


def _snippet(path: Path, terms: set[str], width: int = 240) -> str:
    _, body = read_meta(path)
    best, best_score = "", -1
    for line in body.splitlines():
        clean = line.strip().lstrip(">#-* ").strip()
        if len(clean) < 3:
            continue
        score = len(terms & set(tokenize(clean)))
        if score > best_score:
            best, best_score = clean, score
    return best[:width]


def search(vault: Path, query: str, k: int = 5) -> list[dict]:
    vault = Path(vault)
    docs = refresh(vault)["docs"]
    q = list(dict.fromkeys(tokenize(query)))
    if not q or not docs:
        return []
    n = len(docs)
    avgdl = sum(d["len"] for d in docs.values()) / n or 1
    df = {t: sum(1 for d in docs.values() if t in d["tf"]) for t in q}
    scored = []
    for rel, d in docs.items():
        s = 0.0
        for t in q:
            f = d["tf"].get(t)
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * d["len"] / avgdl))
        if s > 0:
            scored.append((s, rel))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"path": rel, "title": docs[rel]["title"], "name": Path(rel).stem, "score": round(s, 3),
             "snippet": _snippet(vault / rel, set(q))} for s, rel in scored[:k]]
