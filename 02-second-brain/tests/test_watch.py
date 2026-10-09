from pathlib import Path

from second_brain.cli import main
from second_brain.watch import folders


def test_folders_file(tmp_path, monkeypatch):
    (tmp_path / "Drive" / "A").mkdir(parents=True)
    (tmp_path / "Drive" / "B").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    lst = tmp_path / "watch.txt"
    lst.write_text("# synced folders\n~/Drive/*\n\n~/Drive/A   # duplicate\n/nowhere\n")
    assert folders(lst) == [tmp_path / "Drive" / "A", tmp_path / "Drive" / "B", Path("/nowhere")]
    assert folders(tmp_path / "missing.txt") == []


def test_watch_ingests_and_keeps_originals(vault, inbox, tmp_path, capsys):
    lst = tmp_path / "watch.txt"
    lst.write_text(f"{inbox}\n{tmp_path / 'not-synced'}\n")
    before = sorted(p.name for p in inbox.rglob("*") if p.is_file())
    assert main(["watch", "--vault", str(vault), "--list", str(lst), "--dry-run"]) == 1  # one folder missing
    out = capsys.readouterr()
    assert "new, 0 errors" in out.out and "not found" in out.err
    assert sorted(p.name for p in inbox.rglob("*") if p.is_file()) == before  # originals untouched
    assert main(["watch", "--vault", str(vault), "--list", str(lst), "--dry-run"]) == 1
    assert ": 0 new" in capsys.readouterr().out  # second run: everything already filed


def test_watch_without_list(vault, tmp_path, capsys):
    assert main(["watch", "--vault", str(vault), "--list", str(tmp_path / "none.txt")]) == 0
    assert "nothing to do" in capsys.readouterr().out
