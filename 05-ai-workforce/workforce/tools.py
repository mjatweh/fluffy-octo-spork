"""Built-in tools shared by the team. `side_effect=True` tools go through the approval gate."""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import re
import statistics
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from .agent import ToolContext
from .registry import ToolRegistry
from .safety import safe_path

MAX_READ = 20_000


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()

    # --- workspace files (sandboxed) ------------------------------------------------------
    @reg.tool(params={"path": "Path relative to the workspace"})
    def read_file(ctx: ToolContext, path: str) -> str:
        """Read a text file from the team workspace."""
        text = safe_path(ctx.workspace, path).read_text(encoding="utf-8", errors="replace")
        return text if len(text) <= MAX_READ else text[:MAX_READ] + "\n...[truncated]"

    @reg.tool(params={"path": "Path relative to the workspace", "content": "Full file content"})
    def write_file(ctx: ToolContext, path: str, content: str) -> str:
        """Create or overwrite a text file in the team workspace (drafts, lists, plans)."""
        full = safe_path(ctx.workspace, path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {path}"

    @reg.tool(params={"subdir": "Optional sub-directory of the workspace"})
    def list_files(ctx: ToolContext, subdir: str = ".") -> list:
        """List files in the team workspace."""
        root = ctx.workspace.resolve() if subdir in ("", ".") else safe_path(ctx.workspace, subdir)
        if not root.exists():
            return []
        return sorted(str(p.relative_to(ctx.workspace.resolve())) for p in root.rglob("*") if p.is_file())[:200]

    @reg.tool()
    def get_datetime() -> str:
        """Current local date, time and weekday."""
        return dt.datetime.now().strftime("%A %Y-%m-%d %H:%M")

    # --- data analysis ----------------------------------------------------------------------
    @reg.tool(params={"path": "CSV path relative to the workspace",
                      "group_by": "Optional column to group numeric sums by",
                      "columns": "Optional subset of columns to summarize"})
    def analyze_csv(ctx: ToolContext, path: str, group_by: str = "", columns: list[str] | None = None) -> dict:
        """Summary statistics for a CSV (row count, numeric stats, top categorical values, optional group-by sums)."""
        return csv_stats(safe_path(ctx.workspace, path), group_by=group_by, columns=columns)

    # --- research ---------------------------------------------------------------------------
    @reg.tool(params={"url": "http(s) URL to fetch", "max_chars": "Max characters of text to return"})
    def web_fetch(url: str, max_chars: int = 8000) -> str:
        """Fetch a web page and return its readable text."""
        if not re.match(r"^https?://", url):
            raise ValueError("only http(s) URLs are allowed")
        req = urllib.request.Request(url, headers={"User-Agent": "workforce-agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        return html_to_text(raw)[:max_chars]

    # --- second brain -----------------------------------------------------------------------
    @reg.tool(params={"query": "What to look for", "limit": "Max results"})
    def search_knowledge(ctx: ToolContext, query: str, limit: int = 5):
        """Search the Second Brain (Obsidian vault) for notes relevant to a query."""
        return ctx.settings["brain"].search(query, limit=limit)

    @reg.tool(params={"path": "Note path as returned by search_knowledge"})
    def read_note(ctx: ToolContext, path: str) -> str:
        """Read a note from the Second Brain."""
        return ctx.settings["brain"].read_note(path)

    @reg.tool(params={"path": "Note path, e.g. 'Projects/Webinar.md'", "content": "Markdown content"},
              side_effect=True)
    def write_note(ctx: ToolContext, path: str, content: str) -> str:
        """Write a note into the Second Brain vault (needs approval - it is outside the workspace)."""
        return ctx.settings["brain"].write_note(path, content)

    @reg.tool(params={"days": "Look-ahead window in days"})
    def upcoming_dates(ctx: ToolContext, days: int = 14):
        """Upcoming dated items (deadlines, birthdays, events) from the Second Brain."""
        return ctx.settings["brain"].upcoming_dates(days=days)

    # --- integrations with side effects -------------------------------------------------------
    @reg.tool(params={"project": "Sibling project key (see roster)", "args": "CLI arguments, e.g. ['morning']"},
              side_effect=True)
    def run_sibling(ctx: ToolContext, project: str, args: list[str]) -> str:
        """Run an allow-listed command of a sibling project (life dashboard, second brain, exec assistant, content agent)."""
        return run_sibling_cli(ctx.settings.get("siblings", {}), ctx.settings.get("root", Path(".")), project, args)

    @reg.tool(params={"text": "Message body (markdown ok)", "channel": "Optional channel/recipient label"},
              side_effect=True)
    def send_message(ctx: ToolContext, text: str, channel: str = "") -> str:
        """Send a message to the owner: Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) or a
        Slack/Discord/other webhook (WORKFORCE_WEBHOOK_URL or NOTIFY_WEBHOOK_URL)."""
        return deliver_message(text, channel)

    return reg


# --- helpers (pure functions, easy to test) ----------------------------------------------------

def _post_json(url: str, payload: dict) -> int:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def deliver_message(text: str, channel: str = "", env: dict | None = None) -> str:
    env = os.environ if env is None else env
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
        try:
            for part in parts:
                _post_json(f"https://api.telegram.org/bot{token}/sendMessage",
                           {"chat_id": chat, "text": part, "disable_web_page_preview": True})
        except OSError as exc:  # don't echo the URL: it contains the bot token
            return f"Telegram send failed: HTTP {exc.code}" if hasattr(exc, "code") else "Telegram send failed: network error"
        return f"sent to Telegram ({len(parts)} message{'s' * (len(parts) != 1)})"
    url = env.get("WORKFORCE_WEBHOOK_URL") or env.get("NOTIFY_WEBHOOK_URL", "")
    if not url:
        return "No Telegram or webhook configured (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, or WORKFORCE_WEBHOOK_URL); message not sent."
    if "discord.com" in url or "discordapp.com" in url:
        payload = {"content": text[:1990]}
    elif "hooks.slack.com" in url:
        payload = {"text": text}
    else:
        payload = {"text": text, "channel": channel, "content": text}
    return f"sent (HTTP {_post_json(url, payload)})"


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|h\d|li|tr)>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return "\n".join(" ".join(l.split()) for l in text.splitlines() if l.strip())


def _num(v: str) -> float | None:
    v = v.strip().replace(",", "").replace("$", "").replace("%", "")
    try:
        return float(v)
    except ValueError:
        return None


def csv_stats(path: Path, group_by: str = "", columns: list[str] | None = None) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {"rows": 0}
    cols = columns or list(rows[0].keys())
    summary: dict = {"rows": len(rows), "columns": {}}
    numeric_cols = []
    for c in cols:
        vals = [r.get(c, "") or "" for r in rows]
        nums = [n for n in map(_num, vals) if n is not None]
        if nums and len(nums) >= 0.8 * len([v for v in vals if v.strip()]):
            numeric_cols.append(c)
            summary["columns"][c] = {"type": "numeric", "count": len(nums), "sum": round(sum(nums), 4),
                                     "mean": round(statistics.fmean(nums), 4), "median": statistics.median(nums),
                                     "min": min(nums), "max": max(nums)}
        else:
            counts = Counter(v for v in vals if v.strip())
            summary["columns"][c] = {"type": "text", "distinct": len(counts), "top": counts.most_common(5)}
    if group_by:
        groups: dict = defaultdict(lambda: defaultdict(float))
        for r in rows:
            g = r.get(group_by, "")
            groups[g]["_count"] += 1
            for c in numeric_cols:
                if c != group_by and (n := _num(r.get(c, "") or "")) is not None:
                    groups[g][c] += n
        summary["group_by"] = {group_by: {g: {k: round(v, 4) for k, v in d.items()} for g, d in groups.items()}}
    return summary


def run_sibling_cli(siblings: dict, root: Path, project: str, args: list[str], timeout: int = 180) -> str:
    spec = siblings.get(project)
    if not spec:
        raise PermissionError(f"project {project!r} is not allow-listed (known: {', '.join(siblings) or 'none'})")
    if not args or args[0] not in spec.get("commands", []):
        raise PermissionError(f"command {args[:1]} not allowed for {project}; allowed: {spec.get('commands')}")
    if any(a.startswith(("-c", "--exec")) or ";" in a or "|" in a for a in args):
        raise PermissionError("suspicious argument rejected")
    cwd = (root / spec["dir"]).resolve()
    if not cwd.is_dir():
        return f"{project} is not installed at {cwd}"
    proc = subprocess.run([sys.executable, "-m", spec["module"], *args], cwd=cwd, capture_output=True,
                          text=True, timeout=timeout)
    out = (proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr.strip() else "")).strip()
    return f"exit={proc.returncode}\n{out[:MAX_READ]}"
