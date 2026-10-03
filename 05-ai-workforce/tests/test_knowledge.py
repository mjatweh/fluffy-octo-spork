import datetime as dt
import sys

from workforce.knowledge import SecondBrain


def test_fallback_markdown_folder(tmp_path):
    notes = tmp_path / "notes"
    (notes / "Projects").mkdir(parents=True)
    soon = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    (notes / "Projects" / "Webinar.md").write_text(f"# Webinar\nLaunch webinar about AI agents.\nDeadline: {soon}\n")
    (notes / "Recipes.md").write_text("Pasta with tomatoes.\n")
    brain = SecondBrain(sibling_dir=tmp_path / "missing", notes_dir=notes)
    assert brain.api is None and brain.backend.startswith("local markdown")
    hits = brain.search("webinar agents")
    assert hits[0]["path"] == "Projects/Webinar.md" and len(hits) == 1
    assert "nothing" not in str(brain.search("quantum")) and "No notes" in brain.search("quantum")
    assert "Launch webinar" in brain.read_note("Projects/Webinar.md")
    assert brain.write_note("Decisions/2026", "decided") == "wrote Decisions/2026.md"
    assert (notes / "Decisions" / "2026.md").read_text() == "decided"
    assert brain.upcoming_dates(7)[0]["date"] == soon


def test_fallback_write_note_is_sandboxed(tmp_path):
    brain = SecondBrain(sibling_dir=None, notes_dir=tmp_path / "notes")
    try:
        brain.write_note("../evil", "x")
        raise AssertionError("should have raised")
    except ValueError:
        pass


def test_uses_sibling_agent_api_when_present(tmp_path, monkeypatch):
    pkg = tmp_path / "02-second-brain" / "second_brain"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "agent_api.py").write_text(
        "def search(query, k=5, vault=None):\n    return [{'path': 'x.md', 'k': k, 'vault': vault, 'q': query}]\n"
        "def read_note(path, vault=None):\n    return {'path': path, 'content': 'hi'}\n")
    for mod in [m for m in sys.modules if m.startswith("second_brain")]:
        monkeypatch.delitem(sys.modules, mod)
    monkeypatch.setattr(sys, "path", list(sys.path))
    brain = SecondBrain(sibling_dir=pkg.parent, notes_dir=tmp_path / "unused", vault="/my/vault")
    assert brain.backend == "second_brain.agent_api"
    assert brain.search("hello", limit=2) == [{"path": "x.md", "k": 2, "vault": "/my/vault", "q": "hello"}]
    assert brain.read_note("x.md")["content"] == "hi"
    for mod in [m for m in sys.modules if m.startswith("second_brain")]:
        monkeypatch.delitem(sys.modules, mod)
