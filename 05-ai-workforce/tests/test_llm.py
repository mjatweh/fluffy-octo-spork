from types import SimpleNamespace

from workforce.llm import FALLBACK_BETA, AnthropicLLM


class Block:
    def __init__(self, **d):
        self.d = d

    def model_dump(self, **_):
        return self.d


class FakeSDK:
    def __init__(self):
        self.calls = []
        resp = SimpleNamespace(content=[Block(type="text", text="hi"), Block(type="tool_use", id="t", name="x", input={})],
                               stop_reason="tool_use", model="claude-opus-5-5",
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=None))
        create = lambda **kw: self.calls.append(kw) or resp
        self.messages = SimpleNamespace(create=create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


def test_anthropic_llm_request_shape_and_normalization():
    sdk = FakeSDK()
    llm = AnthropicLLM(client=sdk)
    r = llm.create(model="claude-opus-5-5", system="s", messages=[{"role": "user", "content": "q"}],
                   tools=[{"name": "x"}], effort="high")
    kw = sdk.calls[0]
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "high"} and kw["max_tokens"] == 16000 and "thinking" not in kw
    assert r.text == "hi" and r.tool_uses[0]["id"] == "t" and r.content is not r.blocks
    assert r.usage == {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    # models without server-side fallback support use the plain endpoint, no effort when unset
    llm.create(model="claude-haiku-4-5", system="s", messages=[], tools=[])
    assert "betas" not in sdk.calls[1] and "tools" not in sdk.calls[1] and "output_config" not in sdk.calls[1]
