"""Thin Claude wrapper: structured JSON outputs with the brand context prompt-cached."""
from __future__ import annotations

import json
import os

DEFAULT_MODEL = "claude-opus-5-5"
# Models that accept server-side refusal fallbacks (`fallbacks: "default"`).
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


class LLMError(RuntimeError):
    pass


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class LLM:
    def __init__(self, client=None, model: str | None = None, effort: str | None = None):
        self._client = client
        self.model = model or os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
        self.effort = effort or os.environ.get("CLAUDE_EFFORT", "medium")
        self.calls: list[dict] = []  # request kwargs, handy for debugging/tests

    @property
    def client(self):
        if self._client is None:
            import anthropic  # imported lazily so --dry-run works without the SDK
            self._client = anthropic.Anthropic()
        return self._client

    def generate_json(self, system: str, brand_context: str, messages: list[dict], schema: dict,
                      max_tokens: int = 16000) -> dict:
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            # Stable instructions + brand knowledge come first; the breakpoint on the brand block
            # caches it across every generation/revision in a session.
            system=[{"type": "text", "text": system},
                    {"type": "text", "text": brand_context, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": self.effort},
        )
        if self.model in _FALLBACK_MODELS and os.environ.get("CLAUDE_FALLBACKS", "1") != "0":
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        self.calls.append(kwargs)
        resp = self.client.beta.messages.create(**kwargs)
        return parse_response(resp)


def parse_response(resp) -> dict:
    """Extract the JSON payload from a structured-output text block (or a tool_use block)."""
    if resp.stop_reason == "refusal":
        details = getattr(resp, "stop_details", None)
        raise LLMError(f"Claude declined the request ({getattr(details, 'category', None) or 'refusal'})")
    if resp.stop_reason == "max_tokens":
        raise LLMError("response truncated at max_tokens")
    for block in resp.content:
        if block.type == "tool_use":
            return block.input if isinstance(block.input, dict) else json.loads(block.input)
    for block in resp.content:
        if block.type == "text" and block.text.strip():
            try:
                return json.loads(block.text)
            except json.JSONDecodeError as e:
                raise LLMError(f"model returned invalid JSON: {e}") from e
    raise LLMError("no JSON content in response")
