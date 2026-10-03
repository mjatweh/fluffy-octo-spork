"""Runtime configuration (env-driven, no hidden state)."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
STATE_DIR = ".second_brain"  # hidden from Obsidian (dot-folder)
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "vault_template"
GENERATED_BY = "second-brain"


def model() -> str:
    return os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)


def use_fallbacks() -> bool:
    """Server-side refusal fallbacks (beta) - on by default, disable with SECOND_BRAIN_FALLBACKS=0."""
    return os.environ.get("SECOND_BRAIN_FALLBACKS", "1") not in ("0", "false", "no")


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def vault_path(vault: str | os.PathLike | None = None) -> Path:
    """--vault flag > $SECOND_BRAIN_VAULT > $VAULT_PATH (shared with sibling projects) > ./vault"""
    return Path(vault or os.environ.get("SECOND_BRAIN_VAULT") or os.environ.get("VAULT_PATH") or "vault").expanduser().resolve()
