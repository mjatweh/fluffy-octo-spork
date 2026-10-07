"""Configuration loading (TOML via stdlib ``tomllib``)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_DIR / "sample_data"
DEFAULT_MODEL = "claude-opus-5-5"

# Used when no config file exists or when --sample / --dry-run is passed.
SAMPLE_CONNECTORS: list[dict[str, Any]] = [
    {"type": "sample_calendar", "name": "Sample calendar"},
    {"type": "sample_email", "name": "Sample inbox"},
    {"type": "sample_tasks", "name": "Sample tasks"},
]


@dataclass
class Config:
    timezone: str = ""
    output_dir: Path = PROJECT_DIR / "output"
    vault_path: Path | None = None
    publish_dir: Path | None = None  # extra copy of the dashboard, e.g. an iCloud Drive folder for your phone
    model: str = DEFAULT_MODEL
    max_emails: int = 8
    connectors: list[dict[str, Any]] = field(default_factory=lambda: list(SAMPLE_CONNECTORS))
    links: list[dict[str, str]] = field(default_factory=list)
    base_dir: Path = PROJECT_DIR
    source_file: Path | None = None

    @property
    def tz(self) -> tzinfo:
        if self.timezone:
            return ZoneInfo(self.timezone)
        from datetime import datetime

        return datetime.now().astimezone().tzinfo  # system local zone

    def resolve(self, value: str | os.PathLike) -> Path:
        """Resolve a path relative to the config file's directory (``~`` expanded)."""
        p = Path(value).expanduser()
        return p if p.is_absolute() else (self.base_dir / p)

    def use_sample_data(self) -> None:
        self.connectors = list(SAMPLE_CONNECTORS)


# The monorepo-level file shared by all five projects (see ../connections.example.toml).
SHARED_CONNECTIONS = PROJECT_DIR.parent / "connections.toml"


def find_config(explicit: str | None = None) -> Path | None:
    candidates = [explicit, os.environ.get("LIFE_DASHBOARD_CONFIG"), "config.toml", PROJECT_DIR / "config.toml",
                  SHARED_CONNECTIONS]
    for c in candidates:
        if c and Path(c).expanduser().is_file():
            return Path(c).expanduser().resolve()
    if explicit:
        raise FileNotFoundError(f"Config file not found: {explicit}")
    return None


def load_config(path: str | None = None) -> Config:
    found = find_config(path)
    cfg = Config()
    if os.environ.get("VAULT_PATH"):
        cfg.vault_path = Path(os.environ["VAULT_PATH"]).expanduser()
    if os.environ.get("DASHBOARD_PUBLISH_DIR"):
        cfg.publish_dir = Path(os.environ["DASHBOARD_PUBLISH_DIR"]).expanduser()
    if found is None:
        cfg.model = os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
        return cfg

    with open(found, "rb") as fh:
        raw = tomllib.load(fh)
    cfg.source_file = found
    cfg.base_dir = found.parent
    cfg.timezone = raw.get("timezone", "")
    cfg.output_dir = cfg.resolve(raw.get("output_dir", "output"))
    if raw.get("vault_path"):
        cfg.vault_path = cfg.resolve(raw["vault_path"])
    if raw.get("publish_dir"):
        cfg.publish_dir = cfg.resolve(raw["publish_dir"])
    llm = raw.get("llm", {})
    cfg.model = os.environ.get("CLAUDE_MODEL") or llm.get("model") or DEFAULT_MODEL
    cfg.max_emails = int(raw.get("max_emails", cfg.max_emails))
    cfg.connectors = [c for c in raw.get("connectors", []) if c.get("enabled", True)]
    cfg.links = raw.get("links", [])
    return cfg
