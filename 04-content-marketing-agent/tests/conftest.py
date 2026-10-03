import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from content_agent.brand import load_brand  # noqa: E402
from content_agent.llm import LLM  # noqa: E402

EXAMPLE = ROOT / "brand" / "examples"


def text_response(data, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, stop_details=None,
                           content=[SimpleNamespace(type="text", text=json.dumps(data))])


class FakeClient:
    """Stands in for anthropic.Anthropic(): returns queued responses, records request kwargs."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        r = self.responses.pop(0)
        return r if hasattr(r, "content") else text_response(r)


@pytest.fixture
def brand():
    return load_brand(EXAMPLE)


@pytest.fixture
def fake():
    def make(*responses, model=None):
        client = FakeClient(*responses)
        return client, LLM(client=client, model=model)
    return make


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_MODEL", "VAULT_PATH", "BRAND_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
