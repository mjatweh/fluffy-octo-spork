"""Tool registry: plain Python functions + JSON schema, exposed to Claude as client tools."""
from __future__ import annotations

import inspect
import json
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Any]
    side_effect: bool = False  # needs human approval + skipped in dry-run
    wants_ctx: bool = False

    def definition(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    def __call__(self, ctx: Any, **kwargs: Any) -> Any:
        return self.fn(ctx, **kwargs) if self.wants_ctx else self.fn(**kwargs)


def schema_from_signature(fn: Callable, params: dict[str, str] | None = None) -> dict:
    """Build a JSON schema from a function's type hints (the `ctx` parameter is skipped)."""
    params = params or {}
    hints = typing.get_type_hints(fn)
    props: dict[str, dict] = {}
    required: list[str] = []
    for name, p in inspect.signature(fn).parameters.items():
        if name == "ctx":
            continue
        ann = hints.get(name, str)
        origin = typing.get_origin(ann) or ann
        if origin in (typing.Union, types.UnionType):  # Optional[X] / X | None
            args = [a for a in typing.get_args(ann) if a is not type(None)]
            ann = args[0]
            origin = typing.get_origin(ann) or ann
        prop: dict[str, Any] = {"type": _JSON_TYPES.get(origin, "string")}
        if prop["type"] == "array":
            item = (typing.get_args(ann) or (str,))[0]
            prop["items"] = {"type": _JSON_TYPES.get(item, "string")}
        if name in params:
            prop["description"] = params[name]
        props[name] = prop
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> Tool:
        if tool.name in self.tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        self.tools[tool.name] = tool
        return tool

    def tool(self, name: str | None = None, *, description: str | None = None,
             params: dict[str, str] | None = None, side_effect: bool = False):
        """Decorator: @registry.tool(params={"query": "..."}) def search(query: str) -> str: ..."""
        def deco(fn: Callable) -> Callable:
            doc = description or (inspect.getdoc(fn) or fn.__name__).strip()
            self.register(Tool(
                name=name or fn.__name__, description=doc,
                input_schema=schema_from_signature(fn, params), fn=fn, side_effect=side_effect,
                wants_ctx="ctx" in inspect.signature(fn).parameters,
            ))
            return fn
        return deco

    def get(self, name: str) -> Tool:
        if name not in self.tools:
            raise KeyError(f"unknown tool: {name}")
        return self.tools[name]

    def subset(self, names: list[str]) -> list[Tool]:
        return [self.get(n) for n in names]

    def __contains__(self, name: str) -> bool:
        return name in self.tools

    def __iter__(self):
        return iter(self.tools.values())


def validate_input(tool: Tool, data: dict) -> str | None:
    """Minimal schema check (required keys, unknown keys, primitive types). Returns an error or None."""
    if not isinstance(data, dict):
        return "tool input must be an object"
    schema = tool.input_schema
    missing = [k for k in schema.get("required", []) if k not in data]
    if missing:
        return f"missing required field(s): {', '.join(missing)}"
    props = schema.get("properties", {})
    unknown = [k for k in data if k not in props]
    if unknown:
        return f"unknown field(s): {', '.join(unknown)}"
    pytypes = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
    for k, v in data.items():
        want = pytypes.get(props[k].get("type", "string"))
        if want and not isinstance(v, want):
            return f"field {k!r} should be {props[k]['type']}, got {type(v).__name__}"
    return None


def to_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, default=str)
