"""Two-way Telegram bot: ask about your schedule, inbox, tasks and notes from your phone.

Long-polls Telegram's getUpdates, so it needs no public URL or open port. It answers only the chat
in TELEGRAM_CHAT_ID and ignores everyone else. Run it with ``python -m life_dashboard bot``; the
setup wizard installs it as a LaunchAgent that restarts it if it crashes.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .notify import NotifyError, send_telegram, telegram_call

log = logging.getLogger(__name__)

POLL_SECONDS = 50
IDLE_RESET_SECONDS = 30 * 60  # a question after a long pause starts a fresh conversation

HELP = ("Ask me about your day, for example:\n"
        "• What's on my calendar tomorrow?\n"
        "• Any emails I need to answer from Oculi?\n"
        "• When does the Cathcart lease renew?\n"
        "Send /new to start a fresh conversation.")


def load_offset(path: Path) -> int:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return 0


def save_offset(path: Path, offset: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(offset))
    except OSError as exc:
        log.warning("could not save Telegram offset: %s", exc)


def reply_to(assistant: Any, text: str) -> str:
    if text in ("/start", "/help"):
        return HELP
    if text == "/new":
        assistant.reset()
        return "OK, fresh start. What do you want to know?"
    try:
        return assistant.ask(text)
    except Exception as exc:  # the bot must keep running whatever goes wrong with one question
        log.exception("question failed")
        return f"Sorry, I couldn't answer that ({type(exc).__name__}). Try again in a minute."


def handle_updates(updates: list[dict], assistant: Any, token: str, chat_id: str, state: dict) -> int:
    """Answer the messages in one getUpdates batch. Returns the next offset."""
    offset = state.get("offset", 0)
    for update in updates:
        offset = max(offset, update.get("update_id", 0) + 1)
        msg = update.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(chat_id):
            continue  # not you: ignore silently
        text = (msg.get("text") or "").strip()
        if not text:
            send_telegram(token, chat_id, "I can only read text messages for now.")
            continue
        now = time.monotonic()
        if now - state.get("last", now) > IDLE_RESET_SECONDS:
            assistant.reset()
        state["last"] = now
        try:
            telegram_call(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except (NotifyError, OSError):
            pass
        send_telegram(token, chat_id, reply_to(assistant, text))
    state["offset"] = offset
    return offset


def run(assistant: Any, token: str, chat_id: str, offset_file: Path, once: bool = False) -> None:
    state = {"offset": load_offset(offset_file)}
    delay = 5
    log.info("Telegram bot listening")
    while True:
        try:
            data = telegram_call(token, "getUpdates", {"offset": state["offset"], "timeout": 0 if once else POLL_SECONDS,
                                                       "allowed_updates": ["message"]}, timeout=POLL_SECONDS + 15)
            before = state["offset"]
            handle_updates(data.get("result", []), assistant, token, chat_id, state)
            if state["offset"] != before:
                save_offset(offset_file, state["offset"])
            delay = 5
        except (NotifyError, OSError) as exc:  # offline, Mac just woke, Telegram hiccup: wait and retry
            log.warning("Telegram unreachable (%s); retrying in %ss", exc, delay)
            if once:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 300)
        if once:
            return
