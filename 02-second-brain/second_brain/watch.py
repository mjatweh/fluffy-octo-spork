"""Folders that sync to this Mac (OneDrive, Google Drive, Dropbox...) and feed the vault.

``watch_folders.txt`` at the repo root (gitignored) lists one folder per line; ``~`` and ``*``
are expanded and ``#`` starts a comment. ``python -m second_brain watch`` ingests anything new
from them and leaves the originals where they are; files already in the vault are skipped by
content hash, so it is safe to run every day.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

WATCH_FILE = Path(__file__).resolve().parents[2] / "watch_folders.txt"


def folders(path: Path = WATCH_FILE) -> list[Path]:
    if not path.is_file():
        return []
    out: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        expanded = os.path.expanduser(line)
        matches = sorted(glob.glob(expanded)) if any(c in expanded for c in "*?[") else [expanded]
        out += [Path(m) for m in matches if Path(m) not in out]
    return out
