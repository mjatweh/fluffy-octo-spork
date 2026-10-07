import pytest

from life_dashboard import notify
from life_dashboard.briefing import template_briefing
from life_dashboard.pipeline import collect
from life_dashboard.render import render_phone


@pytest.fixture
def posts(monkeypatch):
    calls = []

    def fake_post(url, payload, timeout=15):
        calls.append((url, payload))
        if url.endswith("/getUpdates"):
            return {"ok": True, "result": [
                {"message": {"chat": {"id": 42, "first_name": "Michael", "type": "private"}}},
                {"message": {"chat": {"id": 42, "first_name": "Michael"}}},
            ]}
        return {"ok": True}

    monkeypatch.setattr(notify, "_post", fake_post)
    return calls


def test_chunks_split_on_lines_and_respect_limit():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    parts = notify.chunks(text, limit=1000)
    assert all(len(p) <= 1000 for p in parts) and "".join(parts) == text
    assert notify.chunks("y" * 2500, limit=1000) == ["y" * 1000, "y" * 1000, "y" * 500]


def test_send_prefers_telegram(posts):
    where = notify.send("hello", {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42",
                                  "NOTIFY_WEBHOOK_URL": "https://hooks.slack.com/x"})
    assert where == "Telegram (1 message)"
    url, payload = posts[0]
    assert url == "https://api.telegram.org/bot123:abc/sendMessage"
    assert payload == {"chat_id": "42", "text": "hello", "disable_web_page_preview": True}


def test_send_falls_back_to_webhook(posts):
    assert notify.send("hi", {"NOTIFY_WEBHOOK_URL": "https://discord.com/api/webhooks/1"}) == "webhook"
    assert posts[0][1] == {"content": "hi"}


def test_send_without_config_explains(posts):
    with pytest.raises(notify.NotifyError, match="TELEGRAM_BOT_TOKEN"):
        notify.send("hi", {})


def test_telegram_error_is_reported(monkeypatch):
    monkeypatch.setattr(notify, "_post", lambda url, payload, timeout=15: {"ok": False, "description": "chat not found"})
    with pytest.raises(notify.NotifyError, match="chat not found"):
        notify.send_telegram("t", "1", "x")


def test_find_chats_dedupes(posts):
    assert notify.find_chats("t") == [("42", "Michael")]


def test_render_phone_is_compact(config, day):
    data = collect(config, day)
    text = render_phone(data, template_briefing(data))
    assert text.startswith("Monday, October 5:") and "Schedule" in text and "•" in text
    assert len(text) < notify.TELEGRAM_LIMIT


def test_telegram_command_finds_chat_and_sends_test(posts, monkeypatch, capsys):
    from life_dashboard.cli import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert main(["telegram"]) == 0
    out = capsys.readouterr().out
    assert "TELEGRAM_CHAT_ID=42" in out and "Test message sent" in out
    assert posts[-1][1]["chat_id"] == "42"


def test_telegram_command_without_token_gives_steps(monkeypatch, capsys):
    from life_dashboard.cli import main

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert main(["telegram"]) == 1
    assert "@BotFather" in capsys.readouterr().out


def test_build_notify_sends_briefing(posts, tmp_path, monkeypatch, capsys):
    from life_dashboard.cli import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    assert main(["build", "--dry-run", "-q", "--notify", "--output", str(tmp_path)]) == 0
    assert "Sent to Telegram" in capsys.readouterr().err
    assert "Schedule" in posts[-1][1]["text"]


def test_phone_text_flags_failed_sources(config, day):
    from life_dashboard.models import SourceStatus

    data = collect(config, day)
    data.statuses.append(SourceStatus("Oculi mail", "outlook", "email", ok=False, message="sign-in expired"))
    text = render_phone(data, template_briefing(data))
    assert text.startswith("⚠ Needs attention: Oculi mail: sign-in expired")


def test_build_failure_alerts_phone(posts, tmp_path, monkeypatch):
    from life_dashboard import pipeline
    from life_dashboard.cli import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(pipeline, "collect", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    with pytest.raises(RuntimeError):
        main(["build", "--dry-run", "-q", "--notify", "--output", str(tmp_path)])
    assert "Life Dashboard failed to build: RuntimeError: disk full" in posts[-1][1]["text"]


def test_publish_copies_dashboard(tmp_path, monkeypatch):
    from life_dashboard.cli import main

    pub = tmp_path / "icloud" / "Life Dashboard"
    monkeypatch.setenv("DASHBOARD_PUBLISH_DIR", str(pub))
    assert main(["build", "--dry-run", "-q", "--output", str(tmp_path / "out")]) == 0
    assert "Inbox highlights" in (pub / "dashboard.html").read_text()
    assert (pub / "briefing.md").exists()
