"""Vault filesystem helpers shared by ingest, index, reminders and the agent API."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterator

from . import config, frontmatter

SKIP_DIRS = {".obsidian", config.STATE_DIR, ".trash", ".git", "Attachments", "Templates"}


def init_vault(dest: Path, force: bool = False) -> Path:
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()) and not force:
        raise FileExistsError(f"{dest} exists and is not empty (use --force to merge)")
    shutil.copytree(config.TEMPLATE_DIR, dest, dirs_exist_ok=True)
    return dest


def iter_notes(vault: Path, include_templates: bool = False) -> Iterator[Path]:
    skip = SKIP_DIRS - ({"Templates"} if include_templates else set())
    for p in sorted(vault.rglob("*.md")):
        rel = p.relative_to(vault).parts
        if not any(part in skip or part.startswith(".") for part in rel[:-1]) and not rel[-1].startswith("."):
            yield p


def resolve(vault: Path, rel: str, must_be_md: bool = False) -> Path:
    """Resolve a vault-relative path, refusing anything that escapes the vault."""
    rel = str(rel).strip().lstrip("/\\")
    if must_be_md and not rel.lower().endswith(".md"):
        rel += ".md"
    p = (vault / rel).resolve()
    if p != vault and vault not in p.parents:
        raise ValueError(f"path escapes the vault: {rel}")
    if any(part.startswith(".") for part in p.relative_to(vault).parts):
        raise ValueError(f"hidden/config paths are not accessible: {rel}")
    return p


def read_meta(path: Path) -> tuple[dict, str]:
    return frontmatter.parse(path.read_text(encoding="utf-8", errors="replace"))


def safe_name(s: str, limit: int = 90) -> str:
    s = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")[:limit].strip() or "Untitled"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    i = 2
    while (p := path.with_name(f"{path.stem} {i}{path.suffix}")).exists():
        i += 1
    return p
