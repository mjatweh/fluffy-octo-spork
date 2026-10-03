import os

import pytest

from workforce.agent import execute_tool
from workforce.registry import ToolRegistry
from workforce.safety import Approver, SandboxError, safe_path
from workforce.tools import build_registry


def side_effect_registry(calls):
    reg = ToolRegistry()

    @reg.tool(side_effect=True)
    def send(text: str) -> str:
        """Send something."""
        calls.append(text)
        return "sent"
    return reg


def test_approval_gate_denies_and_allows(make_ctx):
    calls, answers = [], iter(["n", "y"])
    approver = Approver(input_fn=lambda prompt: next(answers), interactive=True)
    tool = side_effect_registry(calls).get("send")
    ctx = make_ctx(approver=approver)
    text, err = execute_tool(tool, {"text": "a"}, ctx)
    assert err and "declined" in text and calls == []
    text, err = execute_tool(tool, {"text": "b"}, ctx)
    assert not err and text == "sent" and calls == ["b"]
    assert [ok for _, ok in approver.log] == [False, True]


def test_auto_yes_and_noninteractive_default_deny(make_ctx):
    calls = []
    tool = side_effect_registry(calls).get("send")
    assert execute_tool(tool, {"text": "x"}, make_ctx(approver=Approver(auto_yes=True)))[0] == "sent"
    text, err = execute_tool(tool, {"text": "y"}, make_ctx(approver=Approver(interactive=False)))
    assert err and calls == ["x"]


def test_dry_run_never_performs_side_effects_or_prompts(make_ctx):
    calls = []
    asked = []
    approver = Approver(input_fn=lambda p: asked.append(p) or "y", interactive=True)
    text, err = execute_tool(side_effect_registry(calls).get("send"), {"text": "x"}, make_ctx(approver=approver, dry_run=True))
    assert "[dry-run]" in text and calls == [] and asked == []


def test_safe_path_rejects_escapes(tmp_path):
    ws = tmp_path / "ws"
    assert safe_path(ws, "notes/a.md") == (ws / "notes/a.md").resolve()
    for bad in ("../secret.txt", "a/../../b", "/etc/passwd", ""):
        with pytest.raises(SandboxError):
            safe_path(ws, bad)
    os.symlink(tmp_path, ws / "link")
    with pytest.raises(SandboxError):
        safe_path(ws, "link/outside.txt")


def test_file_tools_are_sandboxed(make_ctx, tmp_path):
    reg = build_registry()
    ctx = make_ctx()
    assert execute_tool(reg.get("write_file"), {"path": "drafts/a.md", "content": "hello"}, ctx) == ("wrote 5 chars to drafts/a.md", False)
    assert execute_tool(reg.get("read_file"), {"path": "drafts/a.md"}, ctx) == ("hello", False)
    text, err = execute_tool(reg.get("write_file"), {"path": "../escape.md", "content": "x"}, ctx)
    assert err and "SandboxError" in text and not (tmp_path / "escape.md").exists()
    assert "drafts/a.md" in execute_tool(reg.get("list_files"), {}, ctx)[0]
