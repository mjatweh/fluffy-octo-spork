import json
import threading

from workforce.agent import Agent, run_agent
from workforce.llm import fake_response, text_block, tool_use_block
from workforce.llm import ScriptedLLM
from workforce.registry import ToolRegistry


def make_registry(log):
    reg = ToolRegistry()

    @reg.tool()
    def echo(text: str) -> str:
        """Echo text back."""
        log.append(text)
        return f"echo:{text}"

    @reg.tool()
    def boom() -> str:
        """Always fails."""
        raise RuntimeError("kaboom")
    return reg


def agent(**kw):
    return Agent(key="w", name="Worker", role="a worker", instructions="", model="claude-opus-5-5",
                 tools=["echo", "boom"], **kw)


def test_loop_executes_tools_and_stops(make_ctx, usage):
    log = []
    llm = ScriptedLLM([
        fake_response(text_block("let me echo"), tool_use_block("echo", {"text": "hi"}, id="t1")),
        fake_response(text_block("All done: hi")),
    ])
    ctx = make_ctx(agent())
    res = run_agent(agent(), "say hi", llm=llm, registry=make_registry(log), ctx=ctx, usage=usage)
    assert res.output == "All done: hi" and res.turns == 2 and res.stop_reason == "end_turn"
    assert log == ["hi"]
    # tool result fed back on the second request, matched by id
    second = llm.calls[1]["messages"]
    assert second[-1]["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "echo:hi", "is_error": False}
    assert [t["name"] for t in llm.calls[0]["tools"]] == ["echo", "boom"]
    assert usage.total["requests"] == 2 and usage.total["cost_usd"] > 0
    events = [json.loads(l)["type"] for l in ctx.transcript.path.read_text().splitlines()]
    assert events == ["task", "response", "tool_call", "tool_result", "response"]


def test_tool_errors_unknown_tools_and_bad_input_are_returned_not_raised(make_ctx, usage):
    llm = ScriptedLLM([
        fake_response(tool_use_block("boom", {}, id="a"), tool_use_block("nope", {}, id="b"),
                      tool_use_block("echo", {"wrong": 1}, id="c")),
        fake_response(text_block("recovered")),
    ])
    res = run_agent(agent(), "x", llm=llm, registry=make_registry([]), ctx=make_ctx(agent()), usage=usage)
    results = llm.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b", "c"]  # all results, one user message, in order
    assert all(r["is_error"] for r in results)
    assert "kaboom" in results[0]["content"] and "not available" in results[1]["content"]
    assert "missing required" in results[2]["content"]
    assert res.output == "recovered"


def test_max_turn_guard(make_ctx, usage):
    loop_forever = lambda req: fake_response(tool_use_block("echo", {"text": "again"}))
    llm = ScriptedLLM([loop_forever] * 10)
    a = agent(max_turns=3)
    res = run_agent(a, "x", llm=llm, registry=make_registry([]), ctx=make_ctx(a), usage=usage)
    assert res.stop_reason == "max_turns" and res.turns == 3 and len(llm.calls) == 3
    assert "max-turn limit" in res.output


def test_pause_turn_resends_and_refusal_stops(make_ctx, usage):
    llm = ScriptedLLM([fake_response(text_block("searching..."), stop_reason="pause_turn"),
                       fake_response(text_block("final"))])
    res = run_agent(agent(), "x", llm=llm, registry=make_registry([]), ctx=make_ctx(agent()), usage=usage)
    assert res.output == "final" and llm.calls[1]["messages"][-1]["role"] == "assistant"

    llm = ScriptedLLM([fake_response(stop_reason="refusal")])
    res = run_agent(agent(), "x", llm=llm, registry=make_registry([]), ctx=make_ctx(agent()), usage=usage)
    assert res.stop_reason == "refusal"


def test_parallel_tool_calls_run_concurrently(make_ctx, usage):
    barrier = threading.Barrier(3, timeout=5)
    reg = ToolRegistry()

    @reg.tool()
    def wait(i: int) -> str:
        """Blocks until 3 calls are in flight at once."""
        barrier.wait()
        return f"done {i}"

    a = Agent(key="w", name="W", role="r", instructions="", model="m", tools=["wait"])
    llm = ScriptedLLM([fake_response(*[tool_use_block("wait", {"i": i}) for i in range(3)]),
                       fake_response(text_block("ok"))])
    run_agent(a, "x", llm=llm, registry=reg, ctx=make_ctx(a), usage=usage)
    contents = [r["content"] for r in llm.calls[1]["messages"][-1]["content"]]
    assert contents == ["done 0", "done 1", "done 2"]
