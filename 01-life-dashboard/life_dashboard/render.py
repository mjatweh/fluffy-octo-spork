"""Render the dashboard (self-contained HTML), the markdown briefing and the
optional Obsidian daily note."""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from .models import Briefing, DayData

_env = Environment(loader=PackageLoader("life_dashboard", "templates"), autoescape=select_autoescape(["html", "j2"], default_for_string=True))

VAULT_START = "<!-- life-dashboard:start -->"
VAULT_END = "<!-- life-dashboard:end -->"


def render_html(data: DayData, briefing: Briefing, note: str = "") -> str:
    return _env.get_template("dashboard.html.j2").render(d=data, b=briefing, note=note)


def render_markdown(data: DayData, b: Briefing) -> str:
    def section(title: str, items: list[str]) -> list[str]:
        return [f"## {title}", *(f"- {i}" for i in items or ["Nothing notable."]), ""]

    lines = [f"# Daily briefing — {data.day:%A, %B} {data.day.day}, {data.day.year}", "", f"**{b.headline}**", "", b.summary, ""]
    lines += section("Top priorities", [f"{i}" for i in b.top_priorities])
    lines += section("Schedule", b.schedule_highlights)
    lines += section("Emails to reply to", b.emails_to_reply)
    lines += section("Risks & conflicts", b.risks)
    if b.focus_tip:
        lines += ["## Focus tip", b.focus_tip, ""]
    lines += ["## Tasks", *(f"- [ ] {t.title}" + (f" 📅 {t.due}" if t.due else "") for t in data.tasks), ""]
    lines.append(f"_Generated {data.generated_at:%Y-%m-%d %H:%M} by life-dashboard ({b.generated_by})._")
    return "\n".join(lines) + "\n"


def write_vault_note(vault: Path, data: DayData, markdown: str) -> Path:
    """Write/refresh ``<vault>/Daily/YYYY-MM-DD.md``.

    Only the block between the life-dashboard markers is managed, so anything
    you (or other tools) write in the same daily note is preserved.
    """
    path = Path(vault) / "Daily" / f"{data.day.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    block = f"{VAULT_START}\n{markdown.strip()}\n{VAULT_END}"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        pattern = re.compile(re.escape(VAULT_START) + r".*?" + re.escape(VAULT_END), re.S)
        content = pattern.sub(lambda _: block, existing) if pattern.search(existing) else existing.rstrip() + "\n\n" + block + "\n"
    else:
        content = f"---\ndate: {data.day.isoformat()}\ntags: [daily, briefing]\n---\n\n{block}\n"
    path.write_text(content, encoding="utf-8")
    return path
