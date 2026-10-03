import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from life_dashboard.briefing import BRIEFING_SCHEMA, FALLBACK_BETA, generate_briefing, template_briefing
from life_dashboard.pipeline import collect

PAYLOAD = {
    "headline": "Busy morning, free afternoon",
    "summary": "Roadmap review is the big one.",
    "top_priorities": ["Finish the roadmap deck"],
    "schedule_highlights": ["10:00 Q1 roadmap review"],
    "emails_to_reply": ["Priya: pricing doc"],
    "risks": ["1:1 overlaps vendor demo"],
    "focus_tip": "Deck first.",
}


def fake_response(payload=PAYLOAD, stop_reason="end_turn", model="claude-opus-5-5"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        model=model,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(payload))],
    )


@pytest.fixture
def data(config, day):
    return collect(config, day)


def test_template_briefing_is_deterministic(data):
    a, b = template_briefing(data), template_briefing(data)
    assert a == b and a.generated_by == "template"
    assert any("conflict" in r.lower() for r in a.risks)
    assert any("Priya" in e for e in a.emails_to_reply)
    assert a.top_priorities[0].endswith("(overdue)")


def test_claude_briefing_uses_beta_fallback_and_schema(data):
    client = MagicMock()
    client.beta.messages.create.return_value = fake_response()
    briefing, note = generate_briefing(data, "claude-opus-5-5", client=client)

    assert briefing.headline == PAYLOAD["headline"] and briefing.generated_by == "claude-opus-5-5"
    kwargs = client.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["betas"] == [FALLBACK_BETA] and kwargs["fallbacks"] == "default"
    assert kwargs["output_config"]["format"]["schema"] == BRIEFING_SCHEMA
    assert kwargs["output_config"]["effort"] == "medium"
    assert "thinking" not in kwargs and "temperature" not in kwargs
    prompt = kwargs["messages"][0]["content"]
    assert "Q1 roadmap review" in prompt and "<day_data>" in prompt
    client.messages.create.assert_not_called()


def test_other_models_use_plain_messages_api(data):
    client = MagicMock()
    client.messages.create.return_value = fake_response(model="claude-haiku-4-5")
    briefing, _ = generate_briefing(data, "claude-haiku-4-5", client=client)
    kwargs = client.messages.create.call_args.kwargs
    assert "effort" not in kwargs["output_config"] and "fallbacks" not in kwargs
    assert briefing.generated_by == "claude-haiku-4-5"


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_bad_stop_reason_falls_back_to_template(data, stop_reason):
    client = MagicMock()
    client.beta.messages.create.return_value = fake_response(stop_reason=stop_reason)
    briefing, note = generate_briefing(data, "claude-opus-5-5", client=client)
    assert briefing.generated_by == "template" and "failed" in note


def test_api_error_falls_back_to_template(data):
    client = MagicMock()
    client.beta.messages.create.side_effect = ConnectionError("offline")
    briefing, note = generate_briefing(data, "claude-opus-5-5", client=client)
    assert briefing.generated_by == "template" and "offline" in note


def test_offline_and_missing_key_never_call_api(data, monkeypatch):
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", MagicMock(side_effect=AssertionError("no network!")))
    assert generate_briefing(data, "claude-opus-5-5", offline=True)[0].generated_by == "template"
    assert "ANTHROPIC_API_KEY" in generate_briefing(data, "claude-opus-5-5")[1]
