from types import SimpleNamespace
from unittest.mock import MagicMock

from life_dashboard import bot
from life_dashboard.assistant import Assistant
from life_dashboard.briefing import FALLBACK_BETA
from life_dashboard.pipeline import collect


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(name, args, id_="tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id_)


def response(*blocks, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=list(blocks))


def test_assistant_looks_up_the_day_then_answers(config, day):
    client = MagicMock()
    client.beta.messages.create.side_effect = [
        response(tool_use("get_day", {"date": day.isoformat()}), stop="tool_use"),
        response(text("10:00 Q1 roadmap review")),
    ]
    a = Assistant(config, client=client, notes=None, web=False)
    assert a.ask("What's on Monday?") == "10:00 Q1 roadmap review"

    first, second = (c.kwargs for c in client.beta.messages.create.call_args_list)
    assert first["betas"] == [FALLBACK_BETA] and first["fallbacks"] == "default"
    assert [t["name"] for t in first["tools"]] == ["get_day"]
    result = second["messages"][2]["content"][0]  # [question, tool call, tool result, ...]
    assert result["type"] == "tool_result" and "roadmap" in result["content"].lower()
    # follow-ups keep only question/answer text
    assert a.history == [{"role": "user", "content": "What's on Monday?"},
                         {"role": "assistant", "content": "10:00 Q1 roadmap review"}]


def test_tool_errors_go_back_to_claude(config):
    client = MagicMock()
    client.beta.messages.create.side_effect = [
        response(tool_use("get_day", {"date": "not-a-date"}), stop="tool_use"),
        response(text("I couldn't read that date.")),
    ]
    a = Assistant(config, client=client, notes=None)
    assert "couldn't" in a.ask("?")
    result = client.beta.messages.create.call_args_list[1].kwargs["messages"][2]["content"][0]
    assert result["is_error"] is True


def test_day_lookups_are_cached(config, day):
    calls = []

    def collect_fn(cfg, d):
        calls.append(d)
        return collect(cfg, d)

    a = Assistant(config, client=MagicMock(), collect_fn=collect_fn, notes=None)
    a.get_day(day.isoformat())
    a.get_day(day.isoformat())
    assert calls == [day]


def test_note_tools_only_with_a_vault(config, tmp_path):
    notes = MagicMock()
    assert [t["name"] for t in Assistant(config, client=MagicMock(), notes=notes, web=False).tools] == ["get_day"]
    config.vault_path = tmp_path
    names = [t["name"] for t in Assistant(config, client=MagicMock(), notes=notes, web=False).tools]
    assert names == ["get_day", "search_notes", "read_note", "upcoming_dates"]


def test_bot_answers_only_its_owner(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "send_telegram", lambda token, chat, t: sent.append((chat, t)))
    monkeypatch.setattr(bot, "telegram_call", lambda *a, **k: {})
    assistant = MagicMock()
    assistant.ask.return_value = "You're free tomorrow."
    updates = [
        {"update_id": 7, "message": {"chat": {"id": 999}, "text": "hi, who are you?"}},
        {"update_id": 8, "message": {"chat": {"id": 123}, "text": "What's on tomorrow?"}},
        {"update_id": 9, "message": {"chat": {"id": 123}, "text": "/new"}},
    ]
    state = {}
    assert bot.handle_updates(updates, assistant, "tok", "123", state) == 10
    assert sent == [("123", "You're free tomorrow."), ("123", "OK, fresh start. What do you want to know?")]
    assistant.ask.assert_called_once_with("What's on tomorrow?")
    assistant.reset.assert_called_once()


def test_bot_survives_a_failed_question():
    assistant = MagicMock()
    assistant.ask.side_effect = RuntimeError("boom")
    assert "couldn't answer" in bot.reply_to(assistant, "hello")


def test_offset_roundtrip(tmp_path):
    f = tmp_path / "sub" / "offset"
    assert bot.load_offset(f) == 0
    bot.save_offset(f, 42)
    assert bot.load_offset(f) == 42


def test_web_search_tools_location_pause_and_sources(config, monkeypatch):
    monkeypatch.setenv("ASSISTANT_CITY", "Charlotte")
    monkeypatch.setenv("ASSISTANT_REGION", "North Carolina")
    monkeypatch.setenv("ASSISTANT_COUNTRY", "US")
    cite = SimpleNamespace(url="https://example.com/best-pizza", title="Best pizza")
    client = MagicMock()
    client.beta.messages.create.side_effect = [
        response(SimpleNamespace(type="server_tool_use", id="s1"), stop="pause_turn"),
        response(text("Try "), SimpleNamespace(type="text", text="Inizio Pizza", citations=[cite, cite]),
                 text(".")),
    ]
    a = Assistant(config, client=client, notes=None)
    answer = a.ask("Best pizzeria in Charlotte?")
    assert answer == "Try Inizio Pizza.\n\nSources:\nhttps://example.com/best-pizza"
    tools = client.beta.messages.create.call_args_list[0].kwargs["tools"]
    search = next(t for t in tools if t["name"] == "web_search")
    assert search["type"] == "web_search_20260209"
    assert search["user_location"] == {"type": "approximate", "city": "Charlotte", "region": "North Carolina",
                                       "country": "US", "timezone": "America/New_York"}
    assert any(t["name"] == "web_fetch" for t in tools)
    # after a pause the same conversation is sent again to continue
    second = client.beta.messages.create.call_args_list[1].kwargs["messages"]
    assert second[-1]["role"] == "assistant"


def test_web_search_can_be_turned_off(config, monkeypatch):
    monkeypatch.setenv("ASSISTANT_WEB_SEARCH", "0")
    names = [t["name"] for t in Assistant(config, client=MagicMock(), notes=None).tools]
    assert names == ["get_day"]
