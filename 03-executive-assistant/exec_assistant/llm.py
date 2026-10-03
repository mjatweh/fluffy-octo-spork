"""Thin Claude client wrapper with a deterministic dry-run / offline fallback.

Every call site passes a ``fallback`` callable producing a templated response, so
the assistant keeps working with ``--dry-run``, without an API key, or when the
API errors out — a check-in is never lost because the network was down.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

from .config import DEFAULT_MODEL

# Models that accept the server-side refusal fallback ("default" routing).
_SERVER_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _warn(msg: str) -> None:
    print(f"[exec-assistant] {msg}", file=sys.stderr)


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, dry_run: bool = False, client=None,
                 effort: str = "medium", max_tokens: int = 16000):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = client
        self.dry_run = dry_run
        if not dry_run and client is None and not has_credentials():
            _warn("No ANTHROPIC_API_KEY set - using offline templated responses (dry-run).")
            self.dry_run = True

    @property
    def client(self):
        if self._client is None:
            import anthropic  # lazy: dry-run works without the SDK installed
            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, system: str, prompt: str, fallback: Callable[[], str]) -> str:
        if self.dry_run:
            return fallback()
        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if not self.model.startswith("claude-haiku"):
            kwargs["output_config"] = {"effort": self.effort}
        try:
            if self.model in _SERVER_FALLBACK_MODELS:
                resp = self.client.beta.messages.create(
                    betas=[_FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - any API/network failure -> offline template
            _warn(f"Claude call failed ({type(exc).__name__}: {exc}); using templated response.")
            return fallback()
        if getattr(resp, "stop_reason", None) == "refusal":
            _warn("Claude declined this request; using templated response.")
            return fallback()
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        return text or fallback()
