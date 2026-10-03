import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from second_brain import config  # noqa: E402

TODAY = dt.date(2026, 10, 3)


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("SECOND_BRAIN_VAULT", raising=False)


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    shutil.copytree(config.TEMPLATE_DIR, v)
    return v


@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "inbox"
    shutil.copytree(ROOT / "sample_inbox", d)
    return d


@pytest.fixture
def ingested(vault, inbox):
    from second_brain.ingest import ingest

    ingest(inbox, vault, dry_run=True, log=lambda m: None)
    return vault


class FakeClient:
    """Mimics anthropic.Anthropic: client.messages.create / client.beta.messages.create."""

    def __init__(self, reply, stop_reason="end_turn"):
        self.calls = []
        self._reply, self._stop = reply, stop_reason
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        text = self._reply(kw) if callable(self._reply) else self._reply
        if not isinstance(text, str):
            text = json.dumps(text)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=self._stop)


@pytest.fixture
def fake_client():
    return FakeClient
