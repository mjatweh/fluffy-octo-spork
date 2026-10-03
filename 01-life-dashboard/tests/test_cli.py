import pytest

from life_dashboard.cli import load_dotenv, main
from life_dashboard.config import Config
from life_dashboard.schedule import snippet


def test_cli_build_dry_run(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["build", "--dry-run", "--date", "2026-10-05", "--output", str(tmp_path)]) == 0
    assert "# Daily briefing" in capsys.readouterr().out
    assert (tmp_path / "dashboard.html").exists() and (tmp_path / "briefing-2026-10-05.md").exists()


@pytest.mark.parametrize("fmt,needle", [
    ("cron", "30 6 * * *"),
    ("launchd", "<integer>6</integer>"),
    ("systemd", "OnCalendar=*-*-* 06:30:00"),
    ("github", "workflow_dispatch"),
])
def test_schedule_snippets(fmt, needle):
    cfg = Config(timezone="America/New_York")
    out = snippet(fmt, "06:30", cfg, python="/usr/bin/python3")
    assert needle in out and "life_dashboard" in out


def test_github_cron_is_converted_to_utc():
    out = snippet("github", "07:00", Config(timezone="UTC"))
    assert 'cron: "0 7 * * *"' in out


def test_schedule_rejects_bad_time():
    with pytest.raises(ValueError):
        snippet("cron", "25:00", Config())


def test_dotenv_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nexport LD_TEST_A='one'\nLD_TEST_B=two\n")
    monkeypatch.setenv("LD_TEST_B", "keep")
    monkeypatch.delenv("LD_TEST_A", raising=False)
    load_dotenv(env)
    import os

    assert os.environ["LD_TEST_A"] == "one" and os.environ["LD_TEST_B"] == "keep"
    monkeypatch.delenv("LD_TEST_A")
