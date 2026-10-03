"""Run a request through the real anthropic SDK with a mocked HTTP transport (no network)."""
import json

import pytest

anthropic = pytest.importorskip("anthropic")
httpx = pytest.importorskip("httpx2")  # anthropic 1.x uses httpx2

from content_agent import generators, schemas as s  # noqa: E402
from content_agent.llm import LLM  # noqa: E402


def test_real_sdk_serializes_request(brand):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps({"text": "Hours back, not hype."})}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}})

    client = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    res = generators.generate("x", "AI", brand, LLM(client=client))
    assert isinstance(res.content, s.XPost) and res.content.text == "Hours back, not hype."
    body = seen["body"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert "server-side-fallback-2026-07-01" in seen["beta"]
