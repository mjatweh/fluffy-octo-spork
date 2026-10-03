"""Minimal YAML frontmatter read/write (PyYAML used for parsing when installed).

Writes a conservative subset Obsidian's Properties UI understands: scalars,
ISO dates (unquoted) and block lists of scalars.
"""
from __future__ import annotations

import datetime as dt
import json
import re

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PLAIN = re.compile(r"^[A-Za-z0-9][\w .,/()&@+'-]*$")


def split(text: str) -> tuple[str | None, str]:
    """Return (raw_yaml or None, body)."""
    if not text.startswith("---"):
        return None, text
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.S)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def parse(text: str) -> tuple[dict, str]:
    raw, body = split(text)
    if raw is None:
        return {}, body
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            data = {}
    except ImportError:
        data = _mini_parse(raw)
    except Exception:
        data = _mini_parse(raw)
    return {str(k): _norm(v) for k, v in data.items()}, body


def _norm(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10] if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    return v


def _scalar(s: str):
    s = s.strip()
    if s == "" or s in ("null", "~"):
        return None
    if s.startswith('"') and s.endswith('"'):
        try:
            return json.loads(s)
        except ValueError:
            return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1].replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(x) for x in re.split(r",\s*", inner)] if inner else []
    if s in ("true", "false"):
        return s == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _mini_parse(raw: str) -> dict:
    data: dict = {}
    key = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s+(.*)$", line)
        if item and key is not None:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(_scalar(item.group(1)))
            continue
        kv = re.match(r"^([^\s:#][^:]*):(?:\s+(.*))?$", line)
        if kv:
            key = kv.group(1).strip()
            data[key] = _scalar(kv.group(2) or "")
    return data


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    s = str(v)
    if _DATE.match(s) or (_PLAIN.match(s) and s not in ("true", "false", "null") and not re.fullmatch(r"-?[\d.]+", s)):
        return s
    return json.dumps(s, ensure_ascii=False)


def dump(meta: dict) -> str:
    lines = ["---"]
    for k, v in meta.items():
        if v is None or v == [] or v == "":
            continue
        if isinstance(v, (list, tuple)):
            lines.append(f"{k}:")
            lines += [f"  - {_fmt(x)}" for x in v]
        else:
            lines.append(f"{k}: {_fmt(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def render(meta: dict, body: str) -> str:
    return dump(meta) + body.lstrip("\n")
