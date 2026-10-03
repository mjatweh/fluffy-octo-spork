from datetime import date, timedelta

from exec_assistant import checkins
from exec_assistant.demo import seed_week
from exec_assistant.weekly import compute_stats, run_weekly, sparkline, week_label

END = date(2026, 10, 4)  # Sunday -> ISO week 2026-W40


def seed_simple(store, llm):
    # 7 days: 3 priorities each; meeting-heavy days (Tue, Wed) complete 1/3, others 3/3.
    for i in range(7):
        day = (date(2026, 9, 28) + timedelta(days=i)).isoformat()
        heavy = i in (1, 2)
        checkins.run_morning(store, llm, {"priorities": [f"P{i}a", f"P{i}b", f"P{i}c"],
                                          "energy": 4 + i % 4, "meetings": 6 if heavy else 1}, day)
        checkins.run_evening(store, llm, {"completed": "y,n,n" if heavy else "y,y,y",
                                          "energy": 3 + i, "mood": 6,
                                          "root_causes": "meetings" if heavy else "",
                                          "wins": f"win {i}"}, day)


def test_aggregation_math(store, dry_llm):
    seed_simple(store, dry_llm)
    start = date(2026, 9, 28)
    s = compute_stats(store.days(start.isoformat(), END.isoformat()), start, END)
    assert s["week"] == "2026-W40" and s["days_logged"] == 7
    assert s["planned_reviewed"] == 21 and s["completed"] == 17
    assert s["completion_rate"] == round(17 / 21, 3)
    assert s["missed_mornings"] == 0 and s["missed_evenings"] == 0
    # energy per day = mean(am, pm): am = 4 + i%4, pm = 3 + i
    expected = [(4 + i % 4 + 3 + i) / 2 for i in range(7)]
    assert [r["energy"] for r in s["daily"]] == [round(e, 1) for e in expected]
    assert s["avg_energy"] == round(sum(round(e, 1) for e in expected) / 7, 1)
    assert s["energy_trend"] == "rising" and s["energy_slope"] > 0
    assert s["root_causes"][0] == ("meetings", 2) and s["recurring_root_causes"] == ["meetings"]
    assert any("meeting-heavy" in p and "33%" in p and "100%" in p for p in s["patterns"])
    assert s["worst_day"]["date"] in ("2026-09-29", "2026-09-30") and s["best_day"]["rate"] == 1.0
    assert len(s["wins"]) == 7


def test_missing_days_and_carry_over(store, dry_llm):
    checkins.run_morning(store, dry_llm, {"priorities": ["Write memo"], "energy": 5}, "2026-10-01")
    checkins.run_evening(store, dry_llm, {"completed": "n"}, "2026-10-01")
    checkins.run_morning(store, dry_llm, {"priorities": ["write memo "]}, "2026-10-02")  # no evening
    start = date(2026, 9, 28)
    s = compute_stats(store.days(start.isoformat(), END.isoformat()), start, END)
    assert s["days_logged"] == 2 and s["missed_mornings"] == 5 and s["missed_evenings"] == 6
    assert s["planned_reviewed"] == 1 and s["completion_rate"] == 0.0
    assert s["carried_over"] == ["write memo"]


def test_empty_week():
    s = compute_stats([], date(2026, 9, 28), END)
    assert s["completion_rate"] is None and s["avg_energy"] is None and s["best_day"] is None


def test_run_weekly_dry_run_writes_files(store, dry_llm, tmp_path):
    seed_week(store, END, llm=dry_llm)
    vault = tmp_path / "vault"
    res = run_weekly(store, dry_llm, END, out_dir=tmp_path / "reports", vault_path=vault)
    md = res["markdown"]
    for section in ("Keep / Stop / Start", "3 Concrete Improvements", "Proposed Focus", "Patterns"):
        assert section in md
    assert "**Keep:**" in md and "**Stop:**" in md and "**Start:**" in md
    assert res["path"].read_text() == md and res["path"].name == "weekly-2026-W40.md"
    assert (vault / "Weekly" / "2026-W40.md").exists()
    assert store.get_weekly("2026-W40")["stats"]["days_logged"] == 7


def test_run_weekly_mocked_llm(store, dry_llm, mock_llm, fake_client):
    seed_week(store, END, llm=dry_llm)
    res = run_weekly(store, mock_llm, END)
    assert "Mocked Claude reply." in res["markdown"]
    assert "authoritative" in fake_client.messages.calls[0]["messages"][0]["content"]


def test_helpers():
    assert week_label(date(2026, 1, 1)) == "2026-W01"
    assert sparkline([1, 10, None]) == "▁█·"
