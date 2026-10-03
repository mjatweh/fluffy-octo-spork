from exec_assistant.store import Store


def test_checkin_crud(store):
    assert store.get_checkin("2026-10-01", "morning") is None
    store.save_checkin("2026-10-01", "morning", {"priorities": ["a"]}, "brief", energy=7, meetings=2)
    c = store.get_checkin("2026-10-01", "morning")
    assert c["data"] == {"priorities": ["a"]} and c["energy"] == 7 and c["response"] == "brief"
    store.save_checkin("2026-10-01", "morning", {"priorities": ["b"]}, "v2", energy=5)  # upsert
    assert store.get_checkin("2026-10-01", "morning")["data"]["priorities"] == ["b"]
    store.delete_day("2026-10-01")
    assert store.get_checkin("2026-10-01", "morning") is None


def test_priorities_and_tags(store):
    store.set_priorities("2026-10-01", ["x", "y"])
    store.mark_priority("2026-10-01", 1, 0.5)
    assert [(p["text"], p["done"]) for p in store.get_priorities("2026-10-01")] == [("x", None), ("y", 0.5)]
    store.set_priorities("2026-10-01", ["z"])  # replaces
    assert len(store.get_priorities("2026-10-01")) == 1
    store.set_tags("2026-10-01", ["meetings", "scope", "meetings"])
    assert store.get_tags("2026-10-01") == ["meetings", "scope"]


def test_last_checkin_and_days(store):
    for d in ("2026-09-29", "2026-09-30"):
        store.save_checkin(d, "evening", {"n": d}, "r")
    assert store.last_checkin_before("2026-10-01", "evening")["date"] == "2026-09-30"
    assert store.last_checkin_before("2026-09-29", "evening") is None
    assert [d["date"] for d in store.days("2026-09-30", "2026-10-07")] == ["2026-09-30"]


def test_weekly_report_and_file_db(tmp_path):
    s = Store(tmp_path / "sub" / "db.sqlite")
    s.save_weekly("2026-W40", "2026-09-28", "2026-10-04", {"rate": 0.5}, "# md")
    s.close()
    w = Store(tmp_path / "sub" / "db.sqlite").get_weekly("2026-W40")
    assert w["stats"] == {"rate": 0.5} and w["markdown"] == "# md"
