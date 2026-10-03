"""Human-in-the-loop approval gate + workspace sandboxing."""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Callable


class Approver:
    """Asks the human before side-effect tools run. auto_yes=True (--yes) approves everything.

    Non-interactive stdin without --yes means "deny" - a cron job can never silently send things.
    """

    def __init__(self, auto_yes: bool = False, input_fn: Callable[[str], str] | None = None,
                 interactive: bool | None = None):
        self.auto_yes = auto_yes
        self.input_fn = input_fn or input
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self._lock = threading.Lock()  # parallel workers must not interleave prompts
        self.log: list[tuple[str, bool]] = []

    def approve(self, summary: str) -> bool:
        with self._lock:
            if self.auto_yes:
                ok = True
            elif not self.interactive and self.input_fn is input:
                ok = False
            else:
                try:
                    ok = self.input_fn(f"\n[approval] {summary}\nAllow? [y/N] ").strip().lower() in ("y", "yes")
                except EOFError:
                    ok = False
            self.log.append((summary, ok))
            return ok


class SandboxError(ValueError):
    pass


def safe_path(workspace: Path, rel: str) -> Path:
    """Resolve `rel` inside `workspace`, rejecting absolute paths, `..` escapes and symlink escapes."""
    if not rel or rel.strip() == "":
        raise SandboxError("empty path")
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        raise SandboxError(f"path {rel!r} must be relative to the workspace and may not contain '..'")
    root = workspace.resolve()
    full = (root / p).resolve()
    if not full.is_relative_to(root):
        raise SandboxError(f"path {rel!r} escapes the workspace")
    return full
