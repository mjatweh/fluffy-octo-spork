"""The team: Chief of Staff orchestration, delegation (parallel), direct asks and the daily standup."""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import Agent, AgentResult, ToolContext, Transcript, Usage, run_agent
from .config import Config
from .knowledge import SecondBrain
from .safety import Approver
from .tools import build_registry


@dataclass
class TeamResult:
    kind: str                     # run | ask | standup
    goal: str
    output: str
    delegations: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    stop_reason: str = "end_turn"


class Team:
    def __init__(self, config: Config, llm: Any, *, approver: Approver | None = None, dry_run: bool = False,
                 transcript_path: Path | None = None, echo: Any = None):
        self.config, self.llm, self.dry_run = config, llm, dry_run
        self.approver = approver or Approver()
        self.usage = Usage()
        self.transcript = Transcript(transcript_path, echo)
        self.registry = build_registry()
        self._register_delegate()
        self.delegations: list[dict] = []
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(int(config.settings.get("max_parallel", 4)))
        self.workspace = config.workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        vault = os.environ.get("VAULT_PATH")
        self.brain = SecondBrain(sibling_dir=(config.root / "../02-second-brain").resolve(),
                                 notes_dir=Path(vault) if vault else self.workspace / "knowledge",
                                 use_sibling=os.environ.get("WORKFORCE_KNOWLEDGE", "auto") != "local", vault=vault)
        unknown = {t for a in config.agents.values() for t in a.tools if t not in self.registry}
        if unknown:
            raise ValueError(f"roster references unknown tools: {sorted(unknown)}")

    # --- plumbing -----------------------------------------------------------------------------
    def _ctx(self, agent: Agent) -> ToolContext:
        return ToolContext(agent=agent, workspace=self.workspace, approver=self.approver, dry_run=self.dry_run,
                           transcript=self.transcript, team=self,
                           settings={"brain": self.brain, "siblings": self.config.siblings, "root": self.config.root})

    def _run(self, agent: Agent, task: str, team_context: str) -> AgentResult:
        return run_agent(agent, task, llm=self.llm, registry=self.registry, ctx=self._ctx(agent),
                         usage=self.usage, team_context=team_context)

    @property
    def lead(self) -> Agent:
        return self.config.agents[self.config.lead]

    def roster_brief(self) -> str:
        lines = ["Your team (use the key with delegate_task):"]
        for k, a in self.config.specialists.items():
            lines.append(f"- {k} ({a.name}): {a.role}. Tools: {', '.join(a.tools) or 'none'}")
        return "\n".join(lines)

    def worker_context(self) -> str:
        return (f"You are part of an AI workforce led by the {self.lead.name}, working for a busy business owner. "
                f"Today is {time.strftime('%A %Y-%m-%d')}. Workspace files are shared with your teammates.")

    def _register_delegate(self) -> None:
        @self.registry.tool(params={
            "agent": "Specialist key from the roster, e.g. 'researcher'",
            "task": "Clear, self-contained task with the expected deliverable",
            "context": "Background, constraints, prior drafts or revision feedback"})
        def delegate_task(ctx: ToolContext, agent: str, task: str, context: str = "") -> str:
            """Delegate a task to a specialist and get their deliverable back. Call several in one turn to run them in parallel."""
            team: Team = ctx.team
            worker = team.config.find_agent(agent)
            if worker.key == team.config.lead:
                raise ValueError("cannot delegate to yourself")
            res = team.run_specialist(worker, task, context)
            return f"### {worker.name} ({res.turns} turns, stop={res.stop_reason})\n\n{res.output}"

    def run_specialist(self, agent: Agent, task: str, context: str = "") -> AgentResult:
        prompt = task if not context else f"{task}\n\n<context>\n{context}\n</context>"
        with self._lock:
            n = sum(1 for d in self.delegations if d["agent"] == agent.name)
        self.transcript.log(self.lead.name, "delegate", to=agent.name, task=task, revision=n)
        with self._slots:
            started = time.time()
            res = self._run(agent, prompt, self.worker_context())
        with self._lock:
            self.delegations.append({"agent": agent.name, "task": task, "revision": n, "turns": res.turns,
                                     "stop_reason": res.stop_reason, "seconds": round(time.time() - started, 2),
                                     "output": res.output})
        return res

    # --- entry points -------------------------------------------------------------------------
    def run(self, goal: str) -> TeamResult:
        """Chief of Staff plans, delegates (in parallel where possible), reviews and synthesizes."""
        t0 = time.time()
        task = f"Goal from the owner:\n{goal}\n\nPlan the work, delegate to your team, review, then write the final report."
        res = self._run(self.lead, task, self.roster_brief())
        return TeamResult("run", goal, res.output, list(self.delegations), time.time() - t0, res.stop_reason)

    def ask(self, agent_name: str, task: str) -> TeamResult:
        t0 = time.time()
        agent = self.config.find_agent(agent_name)
        ctx = self.roster_brief() if agent.key == self.config.lead else self.worker_context()
        res = self._run(agent, task, ctx)
        return TeamResult("ask", f"{agent.name}: {task}", res.output, list(self.delegations), time.time() - t0, res.stop_reason)

    def standup(self, focus: str = "") -> TeamResult:
        """Daily routine: every specialist reports status in parallel, then the CoS proposes today's plan."""
        t0 = time.time()
        today = time.strftime("%A %Y-%m-%d")
        status_task = (f"Daily standup for {today}. In <=6 bullets: what you can see that needs attention in your area "
                       "(check your tools), blockers, and the single most valuable thing you'd do today."
                       + (f" Focus: {focus}" if focus else ""))
        specialists = list(self.config.specialists.values())
        with ThreadPoolExecutor(max_workers=max(1, len(specialists))) as pool:
            results = list(pool.map(lambda a: self.run_specialist(a, status_task), specialists))
        reports = "\n\n".join(f"### {a.name}\n{r.output}" for a, r in zip(specialists, results))
        synth = (f"It is {today}. Your team just gave their standup updates:\n\n{reports}\n\n"
                 "Write the daily standup report: ## Highlights, ## Blockers & decisions for the owner, "
                 "## Today's plan (max 5 items, each with owner agent and time block), ## Delegations queued. "
                 "Do not delegate again - synthesize." + (f"\nFocus: {focus}" if focus else ""))
        lead = self.lead
        res = run_agent(lead, synth, llm=self.llm, registry=self.registry, ctx=self._ctx(lead), usage=self.usage,
                        team_context=self.roster_brief())
        return TeamResult("standup", f"Daily standup {today}" + (f" - {focus}" if focus else ""), res.output,
                          list(self.delegations), time.time() - t0, res.stop_reason)
