"""Configuration from environment variables (and an optional local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"


def load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env loader: KEY=VALUE lines, never overrides real env vars."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Config:
    data_dir: Path
    vault_path: Path | None
    model: str
    webhook_url: str | None

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        env = os.environ if env is None else env
        vault = env.get("VAULT_PATH") or None
        return cls(
            data_dir=Path(env.get("EA_DATA_DIR") or Path.home() / ".exec_assistant").expanduser(),
            vault_path=Path(vault).expanduser() if vault else None,
            model=env.get("CLAUDE_MODEL") or DEFAULT_MODEL,
            webhook_url=env.get("EA_WEBHOOK_URL") or None,
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "exec_assistant.db"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"
