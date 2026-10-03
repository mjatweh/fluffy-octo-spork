import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exec_assistant.llm import LLM  # noqa: E402
from exec_assistant.store import Store  # noqa: E402


class FakeMessages:
    def __init__(self, text="Mocked Claude reply.", stop_reason="end_turn"):
        self.text, self.stop_reason, self.calls = text, stop_reason, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="thinking", thinking=""),
                                        SimpleNamespace(type="text", text=self.text)])


class FakeClient:
    def __init__(self, **kw):
        self.messages = FakeMessages(**kw)
        self.beta = SimpleNamespace(messages=self.messages)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.delenv("EA_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("EA_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def fake_client():
    return FakeClient()


@pytest.fixture
def mock_llm(fake_client):
    return LLM(client=fake_client)


@pytest.fixture
def dry_llm():
    return LLM(dry_run=True)
