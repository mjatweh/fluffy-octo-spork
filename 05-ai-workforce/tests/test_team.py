import json
import threading

from workforce import cli
from workforce.llm import ScriptedLLM, fake_response, text_block, tool_use_block
from workforce.dryrun import DryRunLLM
from workforce.runs import list_runs, new_run_dir, save_run
from workforce.safety import Approver
from workforce.team import Team


def delegate(agent, task, context=""):
    return tool_use_block("delegate_task", {"agent": agent, "task": task, "context": context})


def test_chief_of_staff_delegates_reviews_and_synthesizes(config):
    script = {
        "Chief of Staff": [
            fake_response(text_block("Plan: research then write."), delegate("researcher", "Find 3 facts")),
            fake_response(text_block("Too vague - revise."), delegate("Researcher", "Revise: add sources", "draft: facts")),
            fake_response(text_block("## Summary\nDone. ## Next actions\n- ship it")),
        ],
        "Researcher": [
            fake_response(text_block("Facts v1")),
            fake_response(text_block("Facts v2 with sources")),
        ],
    }
    llm = ScriptedLLM(script)
    team = Team(config, llm, approver=Approver(auto_yes=True))
    result = team.run("Write a market memo")
    assert "Next actions" in result.output
    assert [d["agent"] for d in result.delegations] == ["Researcher", "Researcher"]
    assert [d["revision"] for d in result.delegations] == [0, 1]
    # the worker saw the revision context, and the CoS got the worker output as a tool_result
    worker_prompts = [c["messages"][0]["content"] for c in llm.calls if c["system"].startswith("You are Researcher")]
    assert "<context>\ndraft: facts\n</context>" in worker_prompts[1]
    cos_calls = [c for c in llm.calls if c["system"].startswith("You are Chief of Staff")]
    assert "Facts v2 with sources" in cos_calls[2]["messages"][-1]["content"][0]["content"]
    assert "researcher (Researcher)" in cos_calls[0]["system"]  # roster brief given to the lead


def test_parallel_delegation_runs_workers_concurrently(config):
    barrier = threading.Barrier(3, timeout=5)

    def worker_reply(name):
        def respond(req):
            barrier.wait()  # deadlocks (BrokenBarrierError) unless all 3 workers are in flight at once
            return fake_response(text_block(f"{name} done"))
        return [respond]

    script = {
        "Chief of Staff": [
            fake_response(delegate("content_marketer", "posts"), delegate("sales_outreach", "emails"),
                          delegate("executive_assistant", "calendar")),
            fake_response(text_block("final report")),
        ],
        "Content Marketer": worker_reply("content"),
        "Sales & Outreach": worker_reply("sales"),
        "Executive Assistant": worker_reply("ea"),
    }
    llm = ScriptedLLM(script)
    result = Team(config, llm).run("Plan the week")
    assert result.output == "final report"
    assert sorted(d["agent"] for d in result.delegations) == ["Content Marketer", "Executive Assistant", "Sales & Outreach"]
    results = llm.calls[-1]["messages"][-1]["content"]
    assert [("content done" in results[0]["content"]), ("sales done" in results[1]["content"])] == [True, True]


def test_delegate_to_unknown_agent_or_self_is_an_error(config):
    llm = ScriptedLLM({"Chief of Staff": [
        fake_response(delegate("astronaut", "fly"), delegate("chief_of_staff", "loop")),
        fake_response(text_block("ok")),
    ]})
    Team(config, llm).run("x")
    results = llm.calls[-1]["messages"][-1]["content"]
    assert all(r["is_error"] for r in results)
    assert "unknown agent" in results[0]["content"] and "yourself" in results[1]["content"]


def test_ask_single_specialist(config):
    llm = ScriptedLLM({"Operations & Finance Analyst": [fake_response(text_block("margin is 40%"))]})
    result = Team(config, llm).ask("ops", "what's our margin?")
    assert result.output == "margin is 40%" and result.kind == "ask"


def test_standup_polls_every_specialist_then_synthesizes(config):
    llm = ScriptedLLM({"*": [lambda req: fake_response(text_block("status ok"))] * 20})
    result = Team(config, llm).standup()
    assert len(result.delegations) == len(config.specialists)
    final = llm.calls[-1]
    assert final["system"].startswith("You are Chief of Staff") and "standup updates" in final["messages"][0]["content"]


def test_dry_run_end_to_end_report_and_history(config, isolated_env):
    run_dir = new_run_dir(config.runs_dir, "Plan next week's content and outreach")
    team = Team(config, DryRunLLM(), dry_run=True, transcript_path=run_dir / "transcript.jsonl")
    result = team.run("Plan next week's content and outreach")
    report = save_run(run_dir, result, team).read_text()
    assert "## Next actions" in report and "## Delegation log" in report and "dry-run" in report
    assert len({d["agent"] for d in result.delegations}) >= 2
    assert any(d["revision"] == 1 for d in result.delegations)  # review round happened
    events = [json.loads(l) for l in (run_dir / "transcript.jsonl").read_text().splitlines()]
    assert any(e["type"] == "side_effect_skipped" for e in events)  # dry-run blocked run_sibling
    assert list_runs(config.runs_dir)[0]["kind"] == "run"


def test_cli_commands_dry_run(capsys, isolated_env):
    assert cli.main(["run", "Plan next week's content and outreach", "--dry-run", "-q"]) == 0
    assert cli.main(["run", "--playbook", "launch-webinar", "--var", "topic=AI agents", "--dry-run", "-q"]) == 0
    assert cli.main(["ask", "researcher", "Summarize trends", "--dry-run", "-q"]) == 0
    assert cli.main(["standup", "--dry-run", "-q"]) == 0
    capsys.readouterr()
    assert cli.main(["history"]) == 0
    out = capsys.readouterr().out
    assert out.count(" dry ") == 4 and "standup" in out
    assert cli.main(["roster"]) == 0 and "Chief of Staff" in capsys.readouterr().out
    assert cli.main(["run", "--playbook", "nope", "--dry-run"]) == 2
    reports = list((isolated_env / "runs").glob("*/report.md"))
    assert len(reports) == 4
