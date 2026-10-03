"""Write drafts to output/ and (optionally) the Obsidian vault at $VAULT_PATH/Content/Drafts/<type>/."""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from .brand import PROJECT_ROOT


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "draft"


def default_out_dir() -> Path:
    return Path(os.environ.get("OUTPUT_DIR") or PROJECT_ROOT / "output")


def vault_path(arg: str | None = None) -> Path | None:
    v = arg or os.environ.get("VAULT_PATH")
    return Path(v).expanduser() if v else None


def frontmatter(meta: dict) -> str:
    def val(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, list):
            return "[" + ", ".join(json.dumps(str(x)) for x in v) + "]"
        return json.dumps(str(v), ensure_ascii=False)  # JSON strings are valid YAML
    return "---\n" + "".join(f"{k}: {val(v)}\n" for k, v in meta.items()) + "---\n\n"


def _unique(path: Path) -> Path:
    n, candidate = 2, path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate


def write_doc(*, kind: str, channel: str, topic: str, title: str, body: str, out_dir: Path | None = None,
              vault: Path | None = None, extra: dict[str, str] | None = None, meta: dict | None = None,
              day: date | None = None) -> list[Path]:
    """Write `<out>/<kind>/<date>-<slug>.md` (+ extra files by suffix) and a vault note if configured.

    kind is the folder/type: social | newsletter | assets | calendar | review.
    """
    day = day or date.today()
    slug = slugify(f"{channel} {topic}" if channel and channel != kind else topic)
    fm = {"type": kind, "channel": channel, "status": "draft", "topic": topic, "created": day.isoformat(),
          **(meta or {}), "tags": ["content", kind, channel]}
    doc = frontmatter(fm) + f"# {title}\n\n{body}"
    paths = []
    folder = (out_dir or default_out_dir()) / kind
    folder.mkdir(parents=True, exist_ok=True)
    md = _unique(folder / f"{day.isoformat()}-{slug}.md")
    md.write_text(doc, encoding="utf-8")
    paths.append(md)
    for suffix, text in (extra or {}).items():
        p = md.with_suffix(suffix)
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    if vault:
        vfolder = vault / "Content" / "Drafts" / kind
        vfolder.mkdir(parents=True, exist_ok=True)
        note = _unique(vfolder / f"{day.isoformat()}-{slug}.md")
        note.write_text(doc, encoding="utf-8")
        paths.append(note)
    return paths
