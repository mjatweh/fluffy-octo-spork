"""Agent definition + the agent loop (Claude tool use with max-turn guard, usage tracking, transcript)."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import Tool, ToolRegistry, to_text, validate_input

# USD per 1M tokens (input, output). Rough estimate only - check current pricing for billing.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0), "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0), "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0), "claude-sonnet-5": (2.0, 10.0), "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0), "dry-run": (0.0, 0.0),
}

SERVER_TOOLS = {"web_search": {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}}


@dataclass
class Agent:
    key: str                      # roster id, e.g. "researcher"
    name: str                     # display name, e.g. "Researcher"
    role: str
    instructions: str
    model: str
    tools: list[str] = field(default_factory=list)
    server_tools: list[str] = field(default_factory=list)
    max_turns: int = 8
    effort: str | None = None
    max_tokens: int = 16000

    def system_prompt(self, team_context: str = "") -> str:
        parts = [f"You are {self.name}, {self.role}.", self.instructions.strip()]
        if team_context:
            parts.append(team_context.strip())
        parts.append("Be concise and concrete. Use tools when they help; when done, reply with your final "
                     "answer in markdown (no tool call).")
        return "\n\n".join(p for p in parts if p)


class Usage:
    """Thread-safe token + cost accumulator, broken down per agent."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.by_agent: dict[str, dict[str, float]] = {}

    def add(self, agent: str, model: str, usage: dict) -> None:
        pin, pout = PRICES.get(model, PRICES["claude-opus-5-5"])
        cost = (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout
                + usage.get("cache_read_input_tokens", 0) * pin * 0.1
                + usage.get("cache_creation_input_tokens", 0) * pin * 1.25) / 1e6
        with self._lock:
            row = self.by_agent.setdefault(agent, {"requests": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
            row["requests"] += 1
            row["input_tokens"] += usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) \
                + usage.get("cache_creation_input_tokens", 0)
            row["output_tokens"] += usage.get("output_tokens", 0)
            row["cost_usd"] += cost

    @property
    def total(self) -> dict[str, float]:
        keys = ("requests", "input_tokens", "output_tokens", "cost_usd")
        with self._lock:
            return {k: sum(r[k] for r in self.by_agent.values()) for k in keys}

    def table(self) -> str:
        lines = ["| Agent | Requests | Input tok | Output tok | Est. cost |", "|---|---:|---:|---:|---:|"]
        for name, r in sorted(self.by_agent.items()):
            lines.append(f"| {name} | {r['requests']} | {r['input_tokens']:,} | {r['output_tokens']:,} | ${r['cost_usd']:.4f} |")
        t = self.total
        lines.append(f"| **Total** | {t['requests']} | {t['input_tokens']:,} | {t['output_tokens']:,} | ${t['cost_usd']:.4f} |")
        return "\n".join(lines)


class Transcript:
    """Append-only JSONL log of every request/response/tool event in a run."""

    def __init__(self, path: Path | None, echo: Any = None):
        self.path = path
        self.echo = echo  # optional callable(event) for live progress output
        self._lock = threading.Lock()
        self.events: list[dict] = []

    def log(self, agent: str, kind: str, **data: Any) -> None:
        event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": agent, "type": kind, **data}
        with self._lock:
            self.events.append(event)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event, default=str) + "\n")
            if self.echo:
                self.echo(event)


@dataclass
class ToolContext:
    """Everything a tool may need at call time."""
    agent: Agent
    workspace: Path
    approver: Any
    dry_run: bool
    transcript: Transcript
    settings: dict = field(default_factory=dict)
    team: Any = None  # set for the Chief of Staff so delegate_task can reach the roster


@dataclass
class AgentResult:
    agent: str
    output: str
    turns: int
    stop_reason: str
    tool_calls: list[dict] = field(default_factory=list)


def execute_tool(tool: Tool, args: dict, ctx: ToolContext) -> tuple[str, bool]:
    """Run one tool call with validation, the approval gate and dry-run handling. Returns (text, is_error)."""
    err = validate_input(tool, args)
    if err:
        return f"Invalid input for {tool.name}: {err}", True
    if tool.side_effect:
        summary = f"{ctx.agent.name} wants to call {tool.name}({json.dumps(args)[:300]})"
        if ctx.dry_run:
            ctx.transcript.log(ctx.agent.name, "side_effect_skipped", tool=tool.name, input=args)
            return f"[dry-run] {tool.name} was NOT executed (side effects are disabled in dry-run).", False
        if not ctx.approver.approve(summary):
            ctx.transcript.log(ctx.agent.name, "approval_denied", tool=tool.name, input=args)
            return f"The human declined to approve {tool.name}. Do not retry; continue without it.", True
    try:
        return to_text(tool(ctx, **args)), False
    except Exception as e:  # tool failures go back to the model, never crash the run
        return f"{type(e).__name__}: {e}", True


def run_agent(agent: Agent, task: str, *, llm: Any, registry: ToolRegistry, ctx: ToolContext,
              usage: Usage, team_context: str = "", parallel_tools: bool = True) -> AgentResult:
    """The agent loop: call Claude, execute requested tools, feed results back, stop on a final answer."""
    tr = ctx.transcript
    tools = registry.subset(agent.tools)
    tool_defs = [t.definition() for t in tools] + [SERVER_TOOLS[s] for s in agent.server_tools if s in SERVER_TOOLS]
    by_name = {t.name: t for t in tools}
    system = agent.system_prompt(team_context)
    messages: list[dict] = [{"role": "user", "content": task}]
    calls: list[dict] = []
    tr.log(agent.name, "task", task=task, model=agent.model)

    last_text, stop = "", "end_turn"
    for turn in range(1, agent.max_turns + 1):
        resp = llm.create(model=agent.model, system=system, messages=messages, tools=tool_defs,
                          max_tokens=agent.max_tokens, effort=agent.effort)
        usage.add(agent.name, resp.model or agent.model, resp.usage)
        tr.log(agent.name, "response", turn=turn, stop_reason=resp.stop_reason, content=resp.blocks, usage=resp.usage)
        last_text = resp.text or last_text
        stop = resp.stop_reason
        messages.append({"role": "assistant", "content": resp.content})

        if stop == "pause_turn":       # server tool (web search) paused a long turn - resend to continue
            continue
        if stop == "refusal":
            return AgentResult(agent.name, last_text or "[declined by safety classifier]", turn, stop, calls)
        uses = resp.tool_uses if stop == "tool_use" else []
        if not uses:
            if stop == "max_tokens":
                last_text += "\n\n[output truncated at max_tokens]"
            return AgentResult(agent.name, last_text, turn, stop, calls)

        def run_one(use: dict) -> dict:
            tool = by_name.get(use["name"])
            if tool is None:
                text, is_err = f"Tool {use['name']!r} is not available to {agent.name}.", True
            else:
                tr.log(agent.name, "tool_call", tool=use["name"], input=use.get("input", {}))
                text, is_err = execute_tool(tool, use.get("input") or {}, ctx)
            tr.log(agent.name, "tool_result", tool=use["name"], is_error=is_err, output=text[:4000])
            calls.append({"tool": use["name"], "input": use.get("input"), "is_error": is_err})
            return {"type": "tool_result", "tool_use_id": use["id"], "content": text, "is_error": is_err}

        if parallel_tools and len(uses) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(uses))) as pool:
                results = list(pool.map(run_one, uses))  # map preserves order
        else:
            results = [run_one(u) for u in uses]
        messages.append({"role": "user", "content": results})  # all results in ONE user message

    tr.log(agent.name, "max_turns", max_turns=agent.max_turns)
    note = f"[stopped: {agent.name} hit the max-turn limit ({agent.max_turns})]"
    return AgentResult(agent.name, f"{last_text}\n\n{note}".strip(), agent.max_turns, "max_turns", calls)
