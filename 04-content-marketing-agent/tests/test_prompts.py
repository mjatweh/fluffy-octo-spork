from content_agent import generators, prompts
from content_agent.llm import DEFAULT_MODEL, LLM


def test_build_prompt_includes_task_topic_constraints():
    p = prompts.build_prompt(prompts.get_type("x-thread"), "AI myths", pillar="AI Without the Hype",
                             source="Long article text", notes="be funny", offer="AI Ops Audit")
    for needle in ("AI myths", "AI Without the Hype", "Long article text", "be funny", "AI Ops Audit",
                   "280 characters"):
        assert needle in p


def test_aliases_and_unknown_type():
    assert prompts.get_type("twitter").key == "x" and prompts.get_type("blog").key == "blog-outline"
    import pytest
    with pytest.raises(KeyError):
        prompts.get_type("fax")


def test_brand_context_contains_brand_and_icp(brand):
    ctx = brand.context()
    assert "Northbeam AI" in ctx and brand.mission in ctx
    assert "Pains" in ctx and "drowning in admin" in ctx and "AI Ops Audit" in ctx
    assert "<banned_words>" in ctx and "synergy" in ctx


def test_request_assembly_sends_cached_brand_context(brand, fake):
    client, llm = fake({"text": "Short tweet about hours back."})
    generators.generate("x", "AI myths", brand, llm)
    req = client.requests[0]
    assert req["model"] == DEFAULT_MODEL == "claude-opus-5-5"
    system = req["system"]
    assert system[0]["text"] == prompts.SYSTEM
    assert "drowning in admin" in system[1]["text"] and brand.mission in system[1]["text"]
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["output_config"]["format"]["schema"]["required"] == ["text"]
    assert "AI myths" in req["messages"][0]["content"]
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]


def test_model_env_override_and_no_fallbacks_for_other_models(brand, fake, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-4-5")
    client, llm = fake({"text": "ok tweet"})
    assert llm.model == "claude-haiku-4-5"
    generators.generate("x", "t", brand, llm)
    assert "fallbacks" not in client.requests[0]
    assert LLM(client=client, model="claude-sonnet-5-5").model == "claude-sonnet-5-5"
