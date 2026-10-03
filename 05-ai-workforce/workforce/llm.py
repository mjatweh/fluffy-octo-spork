"""LLM clients. Every client implements `create(**request) -> LLMResponse`.

- AnthropicLLM: the real Claude Messages API (anthropic SDK).
- ScriptedLLM:  replays a queue of canned responses (tests).
- workforce.dryrun.DryRunLLM: deterministic offline "brain" for --dry-run.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from typing import Any

# Models that accept the server-side refusal fallback (`fallbacks="default"`).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class LLMResponse:
    blocks: list[dict]               # normalized content blocks (JSON-safe), used for logic + transcript
    stop_reason: str
    usage: dict = field(default_factory=dict)
    model: str = ""
    raw_content: Any = None          # what to append back as the assistant turn (SDK objects for real API)

    @property
    def content(self) -> Any:
        return self.raw_content if self.raw_content is not None else self.blocks

    @property
    def text(self) -> str:
        return "\n".join(b.get("text", "") for b in self.blocks if b.get("type") == "text").strip()

    @property
    def tool_uses(self) -> list[dict]:
        return [b for b in self.blocks if b.get("type") == "tool_use"]


class AnthropicLLM:
    def __init__(self, use_fallbacks: bool = True, client: Any = None):
        import anthropic  # imported lazily so dry-run/tests never need the SDK configured
        self.client = client or anthropic.Anthropic()
        self.use_fallbacks = use_fallbacks

    def create(self, *, model: str, system: str, messages: list, tools: list[dict],
               max_tokens: int = 16000, effort: str | None = None) -> LLMResponse:
        params: dict[str, Any] = dict(model=model, system=system, messages=messages, max_tokens=max_tokens)
        if tools:
            params["tools"] = tools
        if effort:
            params["output_config"] = {"effort": effort}
        if self.use_fallbacks and model in FALLBACK_MODELS:
            resp = self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
        else:
            resp = self.client.messages.create(**params)
        u = resp.usage
        usage = {k: getattr(u, k, 0) or 0 for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        blocks = [b.model_dump(mode="json", exclude_none=True) for b in resp.content]
        return LLMResponse(blocks=blocks, stop_reason=resp.stop_reason or "end_turn",
                           usage=usage, model=resp.model, raw_content=resp.content)


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


_ids = itertools.count(1)
_ids_lock = threading.Lock()


def tool_use_block(name: str, input: dict, id: str | None = None) -> dict:
    with _ids_lock:
        n = next(_ids)
    return {"type": "tool_use", "id": id or f"toolu_{n:04d}", "name": name, "input": input}


def fake_response(*blocks: dict, stop_reason: str | None = None, model: str = "fake") -> LLMResponse:
    blocks_l = list(blocks)
    stop = stop_reason or ("tool_use" if any(b["type"] == "tool_use" for b in blocks_l) else "end_turn")
    out = sum(len(str(b)) for b in blocks_l) // 4
    return LLMResponse(blocks=blocks_l, stop_reason=stop, usage={"input_tokens": 100, "output_tokens": out}, model=model)


class ScriptedLLM:
    """Replays responses. Script items are LLMResponse objects or callables(request) -> LLMResponse.

    A dict script maps agent name (detected from the system prompt's first line) to its own queue,
    which keeps parallel workers deterministic.
    """

    def __init__(self, script: list | dict[str, list]):
        self.script = script
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def create(self, **request: Any) -> LLMResponse:
        with self._lock:
            self.calls.append({**request, "messages": list(request["messages"])})  # snapshot
            if isinstance(self.script, dict):
                agent = request["system"].split("\n", 1)[0].removeprefix("You are ").split(",")[0].strip()
                queue = self.script.get(agent) or self.script.get("*")
                if not queue:
                    return fake_response(text_block(f"({agent}: no script left)"))
            else:
                queue = self.script
                if not queue:
                    raise AssertionError("ScriptedLLM ran out of responses")
            item = queue.pop(0)
        return item(request) if callable(item) else item
