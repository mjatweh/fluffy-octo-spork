"""Load roster.toml into Agent objects + settings."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .agent import Agent

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class Config:
    root: Path
    settings: dict
    siblings: dict
    agents: dict[str, Agent]
    lead: str
    playbooks_dir: Path = field(default=PROJECT_ROOT / "playbooks")

    @property
    def workspace(self) -> Path:
        return Path(os.environ.get("WORKFORCE_WORKSPACE") or self.root / self.settings.get("workspace", "workspace"))

    @property
    def runs_dir(self) -> Path:
        return Path(os.environ.get("WORKFORCE_RUNS_DIR") or self.root / self.settings.get("runs_dir", "runs"))

    @property
    def specialists(self) -> dict[str, Agent]:
        return {k: a for k, a in self.agents.items() if k != self.lead}

    def find_agent(self, name: str) -> Agent:
        """Match by key, display name, or unambiguous prefix (case/space/punctuation-insensitive)."""
        norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
        want = norm(name)
        for k, a in self.agents.items():
            if want in (norm(k), norm(a.name)):
                return a
        matches = [a for k, a in self.agents.items() if norm(k).startswith(want) or norm(a.name).startswith(want)]
        if len(matches) == 1:
            return matches[0]
        raise KeyError(f"unknown agent {name!r}; choose from: {', '.join(self.agents)}")


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path or os.environ.get("WORKFORCE_ROSTER") or PROJECT_ROOT / "roster.toml")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    settings = data.get("settings", {})
    default_model = os.environ.get("CLAUDE_MODEL") or settings.get("default_model") or DEFAULT_MODEL
    agents: dict[str, Agent] = {}
    lead = ""
    for key, spec in data.get("agents", {}).items():
        agents[key] = Agent(
            key=key, name=spec.get("name", key.replace("_", " ").title()), role=spec.get("role", "a specialist"),
            instructions=spec.get("instructions", ""), model=spec.get("model") or default_model,
            tools=list(spec.get("tools", [])), server_tools=list(spec.get("server_tools", [])),
            max_turns=int(spec.get("max_turns", 8)), effort=spec.get("effort"),
            max_tokens=int(spec.get("max_tokens", 16000)),
        )
        if spec.get("lead"):
            lead = key
    if not agents:
        raise ValueError(f"{path} defines no [agents.*]")
    lead = lead or next(iter(agents))
    if not settings.get("enable_web_search"):
        for a in agents.values():
            a.server_tools = [s for s in a.server_tools if s != "web_search"]
    return Config(root=path.resolve().parent, settings=settings, siblings=data.get("siblings", {}),
                  agents=agents, lead=lead)
