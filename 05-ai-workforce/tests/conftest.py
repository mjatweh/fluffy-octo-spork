import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workforce.agent import Agent, ToolContext, Transcript, Usage  # noqa: E402
from workforce.config import load_config  # noqa: E402
from workforce.safety import Approver  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own workspace/runs dir, local knowledge fallback, and no API/webhook config."""
    monkeypatch.setenv("WORKFORCE_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("WORKFORCE_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("WORKFORCE_KNOWLEDGE", "local")
    for var in ("VAULT_PATH", "CLAUDE_MODEL", "WORKFORCE_WEBHOOK_URL", "WORKFORCE_ROSTER", "TRADING_DIR",
                "DEALS_DIR", "QUIVER_API_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NOTIFY_WEBHOOK_URL"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "ws").mkdir()
    return tmp_path


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def make_ctx(tmp_path):
    def _make(agent=None, approver=None, dry_run=False, settings=None):
        agent = agent or Agent(key="t", name="Tester", role="a test agent", instructions="", model="claude-opus-5-5")
        return ToolContext(agent=agent, workspace=tmp_path / "ws", approver=approver or Approver(auto_yes=True),
                           dry_run=dry_run, transcript=Transcript(tmp_path / "t.jsonl"), settings=settings or {})
    return _make


@pytest.fixture
def usage():
    return Usage()
