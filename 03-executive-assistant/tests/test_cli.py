import json

from exec_assistant import notify
from exec_assistant.cli import main


def test_end_to_end_answers_then_weekly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path / "vault"))
    for i in range(7):
        day = f"2026-09-{28 + i}" if i < 3 else f"2026-10-0{i - 2}"
        m = tmp_path / f"m{i}.json"
        m.write_text(json.dumps({"date": day, "priorities": ["A", "B", "C"], "energy": 5 + i % 3,
                                 "meetings": 5 if i in (1, 2) else 1}))
        e = tmp_path / f"e{i}.json"
        e.write_text(json.dumps({"date": day, "completed": ["y", "n", "n"] if i in (1, 2) else ["y", "y", "p"],
                                 "didnt_go_well": "meetings all day" if i in (1, 2) else "",
                                 "energy": 6, "mood": 7, "wins": [f"win {i}"]}))
        assert main(["morning", "--dry-run", "--answers", str(m)]) == 0
        assert main(["evening", "--dry-run", "--answers", str(e)]) == 0
    out_file = tmp_path / "week.md"
    assert main(["weekly", "--dry-run", "--end", "2026-10-04", "--out", str(out_file)]) == 0
    out = capsys.readouterr().out
    assert "# Weekly Review 2026-W40" in out and "Keep / Stop / Start" in out
    assert out_file.read_text().startswith("# Weekly Review 2026-W40")
    assert (tmp_path / "vault" / "Daily" / "2026-10-04.md").exists()
    assert main(["stats", "--end", "2026-10-04", "--json"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["planned_reviewed"] == 21 and stats["root_causes"][0] == ["meetings", 2]


def test_seed_demo_history_schedule(capsys, monkeypatch):
    assert main(["seed-demo", "--end", "2026-10-04"]) == 0
    assert main(["history", "--days", "10000"]) == 0
    out = capsys.readouterr().out
    assert "Draft Q4 strategy memo" in out
    assert main(["schedule", "--morning", "07:30", "--weekly", "Fri 17:15"]) == 0
    out = capsys.readouterr().out
    assert "30 7 * * *" in out and "nudge morning" in out and "15 17 * * 5" in out and "weekly --notify" in out


def test_nudge_webhook(monkeypatch, capsys):
    sent = {}
    monkeypatch.setenv("EA_WEBHOOK_URL", "https://hooks.slack.com/services/x")
    monkeypatch.setattr(notify, "desktop", lambda *a: False)
    monkeypatch.setattr(notify, "webhook", lambda url, msg: sent.update(url=url, msg=msg) or True)
    assert main(["nudge", "evening"]) == 0
    assert "evening" in sent["msg"] and "webhook" in capsys.readouterr().err


def test_webhook_payload_shapes():
    assert notify.webhook_payload("https://discord.com/api/webhooks/1", "hi") == {"content": "hi"}
    assert notify.webhook_payload("https://hooks.slack.com/x", "hi") == {"text": "hi"}
    assert set(notify.webhook_payload("https://example.com/hook", "hi")) == {"text", "content"}
