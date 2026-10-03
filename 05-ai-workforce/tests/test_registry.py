import pytest

from workforce.registry import ToolRegistry, schema_from_signature, validate_input
from workforce.tools import build_registry


def test_schema_from_signature_types_required_and_ctx_skipped():
    def f(ctx, query: str, limit: int = 5, tags: list[str] | None = None, ratio: float = 1.0, flag: bool = False):
        """Do things."""
    s = schema_from_signature(f, {"query": "what"})
    assert s["required"] == ["query"]
    assert "ctx" not in s["properties"]
    assert s["properties"]["query"] == {"type": "string", "description": "what"}
    assert s["properties"]["limit"]["type"] == "integer"
    assert s["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}
    assert s["properties"]["ratio"]["type"] == "number"
    assert s["properties"]["flag"]["type"] == "boolean"


def test_decorator_registers_definition_and_calls():
    reg = ToolRegistry()

    @reg.tool(params={"a": "first"})
    def add(a: int, b: int = 1) -> int:
        """Add numbers."""
        return a + b

    tool = reg.get("add")
    assert tool.definition() == {"name": "add", "description": "Add numbers.", "input_schema": tool.input_schema}
    assert tool(None, a=2, b=3) == 5 and not tool.wants_ctx
    with pytest.raises(ValueError):
        reg.tool(name="add")(lambda: None)
    with pytest.raises(KeyError):
        reg.get("nope")


def test_validate_input():
    reg = ToolRegistry()

    @reg.tool()
    def t(name: str, n: int = 0):
        """t"""
    tool = reg.get("t")
    assert validate_input(tool, {"name": "x"}) is None
    assert "missing" in validate_input(tool, {})
    assert "unknown" in validate_input(tool, {"name": "x", "zzz": 1})
    assert "should be integer" in validate_input(tool, {"name": "x", "n": "3"})


def test_builtin_registry_side_effect_flags():
    reg = build_registry()
    for name in ("read_file", "write_file", "list_files", "analyze_csv", "web_fetch", "search_knowledge",
                 "read_note", "write_note", "upcoming_dates", "run_sibling", "send_message", "get_datetime"):
        assert name in reg
    assert {t.name for t in reg if t.side_effect} == {"write_note", "run_sibling", "send_message"}
    for t in reg:  # every schema is a valid object schema Claude accepts
        assert t.input_schema["type"] == "object" and t.description
