import importlib.util
import plistlib
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("setup_wizard", ROOT / "setup_wizard.py")
sw = importlib.util.module_from_spec(spec)
sys.modules["setup_wizard"] = sw
spec.loader.exec_module(sw)


def test_update_env_keeps_comments_replaces_and_appends(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# Claude\nANTHROPIC_API_KEY=\n# GMAIL_APP_PASSWORD=old-comment\nVAULT_PATH=/old\n")
    sw.update_env(env, {"ANTHROPIC_API_KEY": "sk-ant-1", "VAULT_PATH": "/new", "GMAIL_APP_PASSWORD": "abcd"})
    text = env.read_text()
    assert "# Claude\nANTHROPIC_API_KEY=sk-ant-1\n# GMAIL_APP_PASSWORD=old-comment\nVAULT_PATH=/new\n" in text
    assert text.endswith("GMAIL_APP_PASSWORD=abcd\n") and oct(env.stat().st_mode & 0o777) == "0o600"
    assert sw.read_env(env)["GMAIL_APP_PASSWORD"] == "abcd"


def test_render_toml_roundtrips():
    text = sw.render_toml({"timezone": "America/New_York", "skip": ""},
                          {"connectors": [{"type": "imap", "name": 'A "quoted" name', "fyi_domains": ["x.com"],
                                           "unread_only": True, "limit": 5, "empty": []}]})
    data = tomllib.loads(text)
    assert data == {"timezone": "America/New_York", "connectors": [
        {"type": "imap", "name": 'A "quoted" name', "fyi_domains": ["x.com"], "unread_only": True, "limit": 5}]}


def test_connectors_from_example_answers(tmp_path):
    answers = tomllib.loads((ROOT / "setup.example.toml").read_text())
    answers["calendar"][0]["ics_url"] = "https://calendar.google.com/x/basic.ics"
    answers["calendar"][2]["apple_id"] = "me@icloud.com"
    conns = sw.connectors_from(answers, tmp_path / "Vault")
    by = {c["name"]: c for c in conns}
    assert by["Work mail"] == {"type": "imap", "name": "Work mail", "group": "Work", "host": "imap.gmail.com",
                               "username": "you@company.com", "password_env": "WORK_MAIL_PASSWORD",
                               "fyi_domains": ["subsidiary.com"]}
    assert by["Client mail"]["type"] == "outlook" and by["Client mail"]["account"] == "client"
    assert by["Client calendar"]["account"] == by["Client mail"]["account"]  # one sign-in
    assert by["Personal Gmail"]["work_reply_from"] == "you@company.com"
    assert by["iCloud"] == {"type": "icloud", "name": "iCloud", "username": "me@icloud.com",
                            "password_env": "ICLOUD_APP_PASSWORD", "calendars": ["Family"]}
    assert by["Todo"]["path"].endswith("Vault/Todo.md")
    # every generated connector is a type the dashboard knows
    sys.path.insert(0, str(ROOT / "01-life-dashboard"))
    from life_dashboard.connectors import REGISTRY
    assert {c["type"] for c in conns} <= set(REGISTRY)


def test_calendar_without_link_or_apple_id_is_left_out():
    conns = sw.connectors_from({"calendar": [{"name": "G", "provider": "google"},
                                             {"name": "I", "provider": "icloud"}]}, None)
    assert conns == []


def test_launchd_plist_and_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "LOG_DIR", tmp_path / "logs")
    jobs = sw.schedule_jobs(Path("/venv/python"), "06:30")
    assert [j["name"] for j in jobs] == ["dashboard", "checkin-morning", "checkin-evening", "weekly-review",
                                         "telegram-bot", "calendar-copy", "attachments",
                                         "second-brain-folders"]
    assert jobs[0]["hour"] == 6 and jobs[0]["minute"] == 30 and "--notify" in jobs[0]["args"]
    plist = plistlib.loads(sw.launchd_plist("weekly-review", jobs[3]["args"], jobs[3]["workdir"], 18, 0, 0))
    assert plist["Label"] == "com.life-assistant.weekly-review"
    assert plist["StartCalendarInterval"] == {"Hour": 18, "Minute": 0, "Weekday": 0}
    assert plist["ProgramArguments"][0] == "/venv/python"
    bot = plistlib.loads(sw.launchd_plist("telegram-bot", jobs[4]["args"], jobs[4]["workdir"], keep_alive=True))
    assert bot["RunAtLoad"] and bot["KeepAlive"] == {"SuccessfulExit": False}
    assert "StartCalendarInterval" not in bot and bot["ProgramArguments"][-1] == "bot"
    copy = plistlib.loads(sw.launchd_plist("calendar-copy", jobs[5]["args"], jobs[5]["workdir"], every=1800))
    assert copy["StartInterval"] == 1800 and copy["ProgramArguments"][-1] == "mirror"
    assert jobs[6]["hour"] == 5 and jobs[6]["minute"] == 30  # an hour before the dashboard


def test_test_connector_reports_failures_kindly(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "ENV_FILE", tmp_path / ".env")
    ics = ROOT / "01-life-dashboard" / "sample_data" / "calendar.ics"
    ok, detail = sw.test_connector({"type": "ics", "name": "Cal", "source": str(ics)}, "America/New_York")
    assert ok and detail.endswith("item(s) today")
    monkeypatch.delenv("NOPE_PASSWORD", raising=False)
    ok, detail = sw.test_connector({"type": "imap", "name": "Mail", "host": "127.0.0.1", "username": "a@b.c",
                                    "password_env": "NOPE_PASSWORD"}, "")
    assert not ok and "NOPE_PASSWORD" in detail


class ScriptedUI(sw.UI):
    def __init__(self, answers):
        self.answers, self.out = list(answers), []

    def say(self, text=""):
        self.out.append(text)

    def _next(self, *a):
        return self.answers.pop(0)

    ask = secret = _next

    def yes(self, prompt, default=True):
        return self.answers.pop(0)

    def choose(self, prompt, options):
        return self.answers.pop(0)


def test_accounts_step_end_to_end(tmp_path, monkeypatch):
    """Scripted run of the accounts step: secret saved, connection tested, connections.toml written."""
    for name in ("ENV_FILE", "CONNECTIONS", "ANSWERS"):
        monkeypatch.setattr(sw, name, tmp_path / getattr(sw, name).name)
    monkeypatch.setattr(sw, "open_url", lambda url: None)
    monkeypatch.setattr(sw, "IS_MAC", False)
    ics = ROOT / "01-life-dashboard" / "sample_data" / "calendar.ics"
    (tmp_path / "setup.local.toml").write_text(
        f'timezone = "America/New_York"\n[[calendar]]\nname = "Work calendar"\nprovider = "google"\n'
        f'ics_url = "{ics}"\n[[email]]\nname = "Personal Gmail"\nprovider = "gmail"\naddress = "me@gmail.com"\n'
        f'host = "127.0.0.1"\ngroup = "Personal"\nwork_reply_from = "me@company.com"\n')
    ui = ScriptedUI(["abcd efgh ijkl mnop",  # Gmail app password (spaces stripped)
                     2])                     # IMAP can't connect from a test: choose "Skip for now"
    wiz = sw.Wizard(ui)
    wiz.step_accounts()
    assert sw.read_env(tmp_path / ".env")["PERSONAL_GMAIL_PASSWORD"] == "abcdefghijklmnop"
    conns = tomllib.loads((tmp_path / "connections.toml").read_text())["connectors"]
    assert [c["type"] for c in conns] == ["ics", "imap"]
    assert any("✔ Work calendar" in line for line in ui.out)
    assert tomllib.loads((tmp_path / "setup.local.toml").read_text())["email"][0]["secret_env"] == "PERSONAL_GMAIL_PASSWORD"


def test_find_newer_python_prefers_newest(monkeypatch, tmp_path):
    fake = {"python3.12": "/opt/homebrew/bin/python3.12", "python3.11": "/usr/local/bin/python3.11"}
    monkeypatch.setattr(sw.shutil, "which", lambda name: fake.get(name))
    monkeypatch.setattr(sw.os, "access", lambda path, mode: True)
    monkeypatch.setattr(sw, "PY_DIRS", [])
    assert sw.find_newer_python() == "/opt/homebrew/bin/python3.12"
    monkeypatch.setattr(sw.shutil, "which", lambda name: None)
    assert sw.find_newer_python() is None
