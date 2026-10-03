import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from life_dashboard.config import Config  # noqa: E402


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    return Config(timezone="America/New_York", output_dir=tmp_path / "out")


@pytest.fixture
def day():
    return date(2026, 10, 5)  # a Monday
