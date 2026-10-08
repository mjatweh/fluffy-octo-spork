"""Send the briefing to your phone: Telegram bot (preferred) or a generic webhook.

Telegram: set TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID in .env;
``python -m life_dashboard telegram`` finds the chat id for you. Otherwise
NOTIFY_WEBHOOK_URL (Slack / Discord / any JSON endpoint) is used.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import tls

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_LIMIT = 4000  # Telegram caps a message at 4096 characters


class NotifyError(RuntimeError):
    pass


def chunks(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split on line breaks so each piece fits in one message."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # a single huge line
            out.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) > limit:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out


def _post(url: str, payload: dict, timeout: float = 15) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "life-dashboard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=tls.context()) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise NotifyError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise NotifyError(f"can't reach {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from exc
    try:
        return json.loads(body or b"{}")
    except ValueError:
        return {}


def telegram_call(token: str, method: str, payload: dict | None = None) -> dict:
    data = _post(TELEGRAM_API.format(token=token, method=method), payload or {})
    if data and not data.get("ok", True):
        raise NotifyError(f"Telegram: {data.get('description', 'request failed')}")
    return data


def send_telegram(token: str, chat_id: str, text: str) -> int:
    parts = chunks(text)
    for part in parts:
        telegram_call(token, "sendMessage", {"chat_id": chat_id, "text": part, "disable_web_page_preview": True})
    return len(parts)


def webhook_payload(url: str, text: str) -> dict:
    if "discord.com" in url or "discordapp.com" in url:
        return {"content": text[:1990]}
    if "hooks.slack.com" in url:
        return {"text": text}
    return {"text": text, "content": text}


def send(text: str, env: dict | None = None) -> str:
    """Deliver ``text`` to the configured channel. Returns a short description of where it went."""
    env = os.environ if env is None else env
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        n = send_telegram(token, chat, text)
        return f"Telegram ({n} message{'s' * (n != 1)})"
    url = env.get("NOTIFY_WEBHOOK_URL", "")
    if url:
        _post(url, webhook_payload(url, text))
        return "webhook"
    raise NotifyError("nothing configured: set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (or NOTIFY_WEBHOOK_URL) in .env")


def find_chats(token: str) -> list[tuple[str, str]]:
    """``(chat id, name)`` for everyone who has messaged the bot recently."""
    seen: dict[str, str] = {}
    for update in telegram_call(token, "getUpdates").get("result", []):
        msg = update.get("message") or update.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if "id" in chat:
            name = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
            seen[str(chat["id"])] = name or chat.get("username", "")
    return list(seen.items())
