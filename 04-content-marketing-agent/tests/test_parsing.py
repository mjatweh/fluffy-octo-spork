from types import SimpleNamespace

import pytest

from content_agent import generators, schemas as s
from content_agent.llm import LLMError, parse_response


def test_schema_is_strict_and_nested():
    sch = s.schema_for(s.InstagramPost)
    assert sch["additionalProperties"] is False and sch["required"] == ["caption", "hashtags", "slides"]
    slide = sch["properties"]["slides"]["items"]
    assert slide["type"] == "object" and slide["additionalProperties"] is False
    assert sch["properties"]["hashtags"] == {"type": "array", "items": {"type": "string"},
                                             "description": "5-15 hashtags without the # symbol"}
    assert s.schema_for(s.VideoScript)["properties"]["duration_seconds"]["type"] == "integer"


def test_from_dict_builds_dataclasses_and_rejects_missing():
    v = s.from_dict(s.AdCopy, {"variants": [{"angle": "a", "headline": "h", "primary_text": "p", "description": "d"}]})
    assert isinstance(v.variants[0], s.AdVariant) and v.variants[0].headline == "h"
    with pytest.raises(ValueError, match="missing field 'headline'"):
        s.from_dict(s.AdVariant, {"angle": "a"})


def test_parse_tool_use_block():
    resp = SimpleNamespace(stop_reason="tool_use", content=[
        SimpleNamespace(type="text", text="Here you go"),
        SimpleNamespace(type="tool_use", input={"text": "hi"})])
    assert parse_response(resp) == {"text": "hi"}


def test_refusal_and_truncation_raise():
    with pytest.raises(LLMError, match="declined"):
        parse_response(SimpleNamespace(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"), content=[]))
    with pytest.raises(LLMError, match="max_tokens"):
        parse_response(SimpleNamespace(stop_reason="max_tokens", content=[]))


LI = {"hook": "Hours back beat hype.", "body": "Short body about your team.", "cta": "Book a call",
      "hashtags": ["#AI", "Ops", "SmallBusiness"]}


def test_generate_parses_structured_output(brand, fake):
    client, llm = fake(LI)
    res = generators.generate("linkedin", "Hours back", brand, llm)
    assert isinstance(res.content, s.LinkedInPost)
    assert res.content.hashtags == ["AI", "Ops", "SmallBusiness"]  # normalized
    assert res.issues == [] and res.revisions == 0 and len(client.requests) == 1


def test_revise_pass_on_validation_failure(brand, fake):
    bad = {"text": "We leverage AI. " + "x" * 300}
    client, llm = fake(bad, {"text": "We use AI to give your team hours back."})
    res = generators.generate("x", "AI", brand, llm)
    assert res.revisions == 1 and res.issues == []
    revise_msgs = client.requests[1]["messages"]
    assert [m["role"] for m in revise_msgs] == ["user", "assistant", "user"]
    feedback = revise_msgs[2]["content"]
    assert "banned word 'leverage'" in feedback and "max 280" in feedback


def test_revisions_exhausted_enforces_limits(brand, fake):
    long = {"text": "word " * 100}
    client, llm = fake(long, long, long)
    res = generators.generate("x", "AI", brand, llm, max_revisions=2)
    assert len(client.requests) == 3 and res.revisions == 2
    assert res.issues == [] and len(res.content.text) <= 280


def test_schema_mismatch_triggers_revision(brand, fake):
    client, llm = fake({"wrong": 1}, {"text": "fine tweet"})
    res = generators.generate("x", "AI", brand, llm)
    assert res.content.text == "fine tweet"
    assert "did not match schema" in client.requests[1]["messages"][2]["content"]


def test_review_with_mocked_client(brand, fake):
    data = {"overall_score": 40, "voice_score": 30, "icp_score": 50, "summary": "Too hypey.",
            "strengths": ["short"], "issues": ["uses leverage"],
            "suggested_edits": [{"original": "leverage", "suggestion": "use", "reason": "banned"}],
            "revised_draft": "We use AI."}
    client, llm = fake(data)
    rev = generators.review("We leverage AI.", brand, llm, channel="linkedin")
    assert rev.overall_score == 40 and rev.suggested_edits[0].suggestion == "use"
    assert "We leverage AI." in client.requests[0]["messages"][0]["content"]
