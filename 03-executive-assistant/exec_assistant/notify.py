"""Notification hooks: desktop (notify-send / osascript), Telegram bot and generic webhooks (stdlib urllib)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request


def desktop(title: str, message: str) -> bool:
    if shutil.which("notify-send"):
        cmd = ["notify-send", title, message[:500]]
    elif shutil.which("osascript"):
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
        cmd = ["osascript", "-e", f'display notification "{esc(message[:500])}" with title "{esc(title)}"']
    else:
        return False
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def webhook_payload(url: str, message: str) -> dict:
    """Shape the JSON body for common services; unknown URLs get both common keys."""
    if "discord.com" in url or "discordapp.com" in url:
        return {"content": message[:1990]}
    if "hooks.slack.com" in url:
        return {"text": message}
    if "api.telegram.org" in url:  # e.g. https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>
        return {"text": message[:4000]}
    return {"text": message, "content": message}


def webhook(url: str, message: str, timeout: float = 10) -> bool:
    req = urllib.request.Request(
        url, data=json.dumps(webhook_payload(url, message)).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "exec-assistant/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except OSError as exc:  # URLError/HTTPError/timeouts are all OSError subclasses
        print(f"[exec-assistant] webhook failed: {exc}", file=sys.stderr)
        return False


def chunks(text: str, limit: int = 4000) -> list[str]:
    """Split on line breaks into pieces that fit one Telegram message (max 4096 chars)."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            out.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) > limit:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out


def telegram(token: str, chat_id: str, message: str, timeout: float = 10) -> bool:
    """Send via the Telegram Bot API (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID), splitting long reports."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        for part in chunks(message):
            body = json.dumps({"chat_id": chat_id, "text": part, "disable_web_page_preview": True}).encode()
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json", "User-Agent": "exec-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if not 200 <= resp.status < 300:
                    return False
        return True
    except OSError as exc:  # never print the URL: it contains the bot token
        detail = f"HTTP {exc.code}" if hasattr(exc, "code") else getattr(exc, "reason", type(exc).__name__)
        print(f"[exec-assistant] Telegram failed: {detail}", file=sys.stderr)
        return False


def send(title: str, message: str, webhook_url: str | None = None,
         use_desktop: bool = True, env: dict | None = None) -> list[str]:
    """Print the nudge and fan out to whatever channels are available. Returns channels used."""
    env = os.environ if env is None else env
    print(f"{title}\n{message}")
    sent = ["stdout"]
    if use_desktop and desktop(title, message):
        sent.append("desktop")
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")
    if token and chat and telegram(token, chat, f"{title}\n{message}"):
        sent.append("telegram")
    if webhook_url and webhook(webhook_url, f"*{title}*\n{message}"):
        sent.append("webhook")
    return sent


NUDGES = {
    "morning": ("Morning check-in", "Good morning! Set your top 3 priorities: "
                "`python -m exec_assistant morning`"),
    "evening": ("Evening review", "Time to close the day - what went well, what didn't? "
                "`python -m exec_assistant evening`"),
    "weekly": ("Weekly rollup", "Your week is done. Generate the rollup: "
               "`python -m exec_assistant weekly`"),
}
