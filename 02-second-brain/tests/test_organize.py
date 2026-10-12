import json
from pathlib import Path

import pytest

from second_brain import organize as org
from second_brain.cli import main

LAYOUT = """
destination = "{dest}"
sources = ["{src}"]
subfolders = ["01 Legal & Corporate", "02 Accounting", "04 Tax", "05 Insurance"]
property_subfolders = ["10 Acquisition & Closing", "12 Leasing & Tenants"]

[[entity]]
category = "1 Tech"
name = "Oculi"
aliases = ["oculi", "fris inc"]

[[entity]]
category = "2 Real Estate"
name = "3480 Lakemont"
aliases = ["lakemont", "laffoday"]
property = true

[[entity]]
category = "5 Personal"
subfolders = ["Insurance", "Taxes"]
"""


@pytest.fixture
def setup(tmp_path):
    src, dest = tmp_path / "Downloads", tmp_path / "Files"
    (src / "deep").mkdir(parents=True)
    (src / ".hidden").mkdir()
    (src / "MyApp.app").mkdir()
    (src / "Lakemont Operating Agreement.txt").write_text("Operating agreement of Saleh Lakemont LLC")
    (src / "deep" / "Oculi invoice 12.txt").write_text("Invoice from vendor to Fris Inc")
    (src / "random.txt").write_text("grocery list")
    (src / "setup.dmg").write_text("x")
    (src / ".hidden" / "secret.txt").write_text("x")
    (src / "MyApp.app" / "Info.txt").write_text("x")
    layout_file = tmp_path / "layout.toml"
    layout_file.write_text(LAYOUT.format(dest=dest, src=src))
    return org.load_layout(layout_file), layout_file, src, dest


def test_layout_and_init(setup):
    layout, _, _, dest = setup
    lake = layout.entity("2 Real Estate/3480 Lakemont")
    assert "10 Acquisition & Closing" in lake.subfolders and "01 Legal & Corporate" in lake.subfolders
    assert "10 Acquisition & Closing" not in layout.entity("1 Tech/Oculi").subfolders
    assert layout.entity("5 Personal").subfolders == ["Insurance", "Taxes"]
    org.init_tree(layout)
    assert (dest / "2 Real Estate" / "3480 Lakemont" / "12 Leasing & Tenants").is_dir()
    assert (dest / "5 Personal" / "Taxes").is_dir() and (dest / "00 To Sort").is_dir()
    assert org.init_tree(layout) == 0


def test_candidates_skip_hidden_apps_and_non_documents(setup):
    layout, _, src, _ = setup
    names = sorted(p.name for p in org.candidates(layout))
    assert names == ["Lakemont Operating Agreement.txt", "Oculi invoice 12.txt", "random.txt"]


def test_offline_plan_apply_undo(setup):
    layout, _, src, dest = setup
    rows = {Path(r["source"]).name: r for r in org.plan(layout, None, log=lambda m: None)}
    assert rows["Lakemont Operating Agreement.txt"]["destination_folder"] == str(
        dest / "2 Real Estate" / "3480 Lakemont" / "01 Legal & Corporate")
    assert rows["Oculi invoice 12.txt"]["destination_folder"] == str(dest / "1 Tech" / "Oculi" / "02 Accounting")
    assert rows["random.txt"]["destination_folder"] == str(dest / "00 To Sort")

    undo_log = dest / "undo.jsonl"
    (dest / "1 Tech" / "Oculi" / "02 Accounting").mkdir(parents=True)
    (dest / "1 Tech" / "Oculi" / "02 Accounting" / "Oculi invoice 12.txt").write_text("older copy")
    moved, _ = org.apply(list(rows.values()), undo_log, log=lambda m: None)
    assert moved == 3 and not (src / "random.txt").exists()
    assert (dest / "1 Tech" / "Oculi" / "02 Accounting" / "Oculi invoice 12 (2).txt").read_text().startswith("Invoice")
    org.undo(undo_log, log=lambda m: None)
    assert (src / "deep" / "Oculi invoice 12.txt").read_text().startswith("Invoice")
    assert (src / "random.txt").exists()
    assert (dest / "1 Tech" / "Oculi" / "02 Accounting" / "Oculi invoice 12.txt").read_text() == "older copy"


def test_claude_plan_low_confidence_goes_to_to_sort(setup, fake_client):
    layout, _, _, dest = setup
    files = org.candidates(layout)

    def reply(kw):
        assert "3480 Lakemont" in kw["system"][1]["text"]
        return {"files": [
            {"id": 0, "entity": "2 Real Estate/3480 Lakemont", "subfolder": "10 Acquisition & Closing", "confidence": "high"},
            {"id": 1, "entity": "1 Tech/Oculi", "subfolder": "10 Acquisition & Closing", "confidence": "medium"},
            {"id": 2, "entity": "5 Personal", "subfolder": "Taxes", "confidence": "low"},
        ]}

    rows = org.plan(layout, fake_client(reply), log=lambda m: None, files=files)
    got = {Path(r["source"]).name: r["destination_folder"] for r in rows}
    assert got["Lakemont Operating Agreement.txt"].endswith("3480 Lakemont/10 Acquisition & Closing")
    assert got["Oculi invoice 12.txt"] == str(dest / "1 Tech" / "Oculi")  # subfolder not valid for Oculi
    assert got["random.txt"] == str(dest / "00 To Sort")
    assert all(r["how"] == "claude" for r in rows)


def test_cli_roundtrip(setup, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(org, "STATE_DIR", tmp_path / "state")
    _, layout_file, src, dest = setup
    assert main(["organize", "init", "--layout", str(layout_file)]) == 0
    assert main(["organize", "plan", "--layout", str(layout_file), "--offline"]) == 0
    assert "Nothing has moved yet" in capsys.readouterr().out
    assert (src / "random.txt").exists()
    assert main(["organize", "apply", "--layout", str(layout_file)]) == 0
    assert (dest / "00 To Sort" / "random.txt").exists()
    assert main(["organize", "undo", "--layout", str(layout_file)]) == 0
    assert (src / "random.txt").exists()


def test_missing_layout(tmp_path, capsys):
    assert main(["organize", "plan", "--layout", str(tmp_path / "none.toml")]) == 2


def test_category_folder_sets_and_nesting(tmp_path):
    f = tmp_path / "layout.toml"
    f.write_text(f"""
destination = "{tmp_path / 'Files'}"
[category_subfolders]
"1 REAL ESTATE" = ["01 CONSTRUCTION", "02 CONTRACTS & LEGAL"]

[[entity]]
category = "1 REAL ESTATE"
name = "GATEWAY (MT HOLLY)/MOB (GATEWAY CENTER ONE)"

[[entity]]
category = "1 REAL ESTATE"
name = "LVNT"
extra_subfolders = ["02 CONTRACTS & LEGAL/HR & EMPLOYMENT"]
""")
    layout = org.load_layout(f)
    mob = layout.entity("1 REAL ESTATE/GATEWAY (MT HOLLY)/MOB (GATEWAY CENTER ONE)")
    assert mob.subfolders == ["01 CONSTRUCTION", "02 CONTRACTS & LEGAL"]
    assert layout.entity("1 REAL ESTATE/LVNT").subfolders[-1] == "02 CONTRACTS & LEGAL/HR & EMPLOYMENT"
    org.init_tree(layout)
    assert (tmp_path / "Files/1 REAL ESTATE/GATEWAY (MT HOLLY)/MOB (GATEWAY CENTER ONE)/01 CONSTRUCTION").is_dir()
    assert (tmp_path / "Files/1 REAL ESTATE/LVNT/02 CONTRACTS & LEGAL/HR & EMPLOYMENT").is_dir()


def test_resort_the_to_sort_folder(setup, monkeypatch, tmp_path):
    monkeypatch.setattr(org, "STATE_DIR", tmp_path / "state")
    layout, layout_file, src, dest = setup
    todo = dest / "00 To Sort"
    todo.mkdir(parents=True)
    (todo / "Laffoday deed.txt").write_text("deed")
    (todo / "_organize-plan.csv").write_text("x")
    assert main(["organize", "plan", "--layout", str(layout_file), "--offline", "--from", str(todo)]) == 0
    rows = org.read_plan(todo / "_organize-plan.csv")
    assert [Path(r["source"]).name for r in rows] == ["Laffoday deed.txt"]
    assert "3480 Lakemont" in rows[0]["destination_folder"]


def test_deep_plan_uses_more_text_and_effort(setup, fake_client, monkeypatch):
    layout, _, _, _ = setup
    seen = []

    def reply(kw):
        seen.append(kw["output_config"]["effort"])
        return {"files": []}

    monkeypatch.setattr(org, "excerpt", lambda p, chars=org.EXCERPT_CHARS: str(chars))
    org.plan(layout, fake_client(reply), log=lambda m: None, files=org.candidates(layout), deep=True)
    assert seen == ["medium"]


def test_new_plan_never_overwrites_old_one(setup, capsys, tmp_path):
    layout, layout_file, src, dest = setup
    assert main(["organize", "plan", "--layout", str(layout_file), "--offline"]) == 0
    plan_file = dest / "00 To Sort" / "_organize-plan.csv"
    first = plan_file.read_text()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["organize", "plan", "--layout", str(layout_file), "--offline", "--from", str(empty)]) == 0
    assert plan_file.read_text() == first  # empty run leaves the plan alone
    assert main(["organize", "plan", "--layout", str(layout_file), "--offline"]) == 0
    assert len(list((dest / "00 To Sort").glob("_organize-plan-previous-*.csv"))) == 1
