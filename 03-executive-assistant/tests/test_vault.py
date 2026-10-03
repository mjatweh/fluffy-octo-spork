from exec_assistant import checkins, vault


def test_upsert_preserves_foreign_content(tmp_path):
    note = tmp_path / "Daily" / "2026-10-01.md"
    note.parent.mkdir(parents=True)
    original = "---\ntags: [daily]\n---\n# 2026-10-01\n\n## Life Dashboard briefing\nWeather: sunny\n"
    note.write_text(original)
    vault.write_evening(tmp_path, "2026-10-01", "evening v1")
    vault.write_morning(tmp_path, "2026-10-01", "morning v1")
    text = note.read_text()
    assert text.startswith(original.rstrip("\n"))
    assert text.index("## Morning check-in") < text.index("## Evening review")  # morning inserted above
    # Someone else appends after us; replacing our section must not touch it.
    note.write_text(text + "\n## Notes\nmy own notes\n")
    vault.write_morning(tmp_path, "2026-10-01", "morning v2")
    text = note.read_text()
    assert "morning v2" in text and "morning v1" not in text and text.count("## Morning check-in") == 1
    assert "my own notes" in text and "Weather: sunny" in text and "evening v1" in text


def test_new_file_and_checkin_integration(store, dry_llm, tmp_path):
    checkins.run_morning(store, dry_llm, {"priorities": ["A"], "energy": 6}, "2026-10-02", tmp_path)
    checkins.run_evening(store, dry_llm, {"completed": "y", "wins": "shipped"}, "2026-10-02", tmp_path)
    text = (tmp_path / "Daily" / "2026-10-02.md").read_text()
    assert text.startswith("# 2026-10-02")
    assert "- [ ] A" in text and "- [x] A" in text and "shipped" in text
    checkins.run_evening(store, dry_llm, {"completed": "n"}, "2026-10-02", tmp_path)  # re-run replaces
    text = (tmp_path / "Daily" / "2026-10-02.md").read_text()
    assert text.count("## Evening review") == 1 and "- [ ] A" in text.split("## Evening review")[1]
