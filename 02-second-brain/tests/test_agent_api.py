import datetime as dt
import json
from types import SimpleNamespace

import pytest

from second_brain import agent_api


def test_python_api(ingested):
    hits = agent_api.search("lease renewal", k=2, vault=ingested)
    assert len(hits) == 2 and hits[0]["name"] == "Residential Lease Agreement"
    note = agent_api.read_note(hits[0]["path"], vault=ingested)
    assert note["frontmatter"]["renewal_date"] == "2027-03-01"
    assert agent_api.read_note("Residential Lease Agreement", vault=ingested)["path"] == hits[0]["path"]  # bare name
    rows = agent_api.upcoming_dates(60, vault=ingested, today=dt.date(2026, 10, 3))
    assert rows[0]["label"] == "due"
    assert any(n["path"] == "Life Admin/Insurance/Auto Insurance Policy Declarations.md"
               for n in agent_api.list_notes("Life Admin", vault=ingested))


def test_write_note_modes_and_search(ingested):
    agent_api.write_note("Daily/2026-10-04", "# Oct 4\nCall the plumber about the leak.", vault=ingested)
    agent_api.write_note("Daily/2026-10-04.md", "## Exec assistant briefing\n- Insurance expires soon", mode="append", vault=ingested)
    text = (ingested / "Daily/2026-10-04.md").read_text()
    assert text.startswith("# Oct 4") and "Exec assistant briefing" in text
    assert agent_api.search("plumber leak", vault=ingested)[0]["path"] == "Daily/2026-10-04.md"
    with pytest.raises(FileExistsError):
        agent_api.write_note("Daily/2026-10-04.md", "x", mode="create", vault=ingested)


def test_env_default_vault(ingested, monkeypatch):
    monkeypatch.setenv("SECOND_BRAIN_VAULT", str(ingested))
    assert agent_api.search("lease")[0]["name"] == "Residential Lease Agreement"


@pytest.mark.parametrize("bad", ["../escape.md", "/../../etc/passwd", ".obsidian/app.json"])
def test_path_safety(ingested, bad):
    with pytest.raises(ValueError):
        agent_api.write_note(bad, "nope", vault=ingested)


def test_tool_schemas():
    names = [t["name"] for t in agent_api.TOOLS]
    assert names == agent_api.TOOL_NAMES == ["vault_search", "vault_read_note", "vault_write_note",
                                             "vault_upcoming_dates", "vault_list_notes"]
    for t in agent_api.TOOLS:
        s = t["input_schema"]
        assert s["type"] == "object" and s["additionalProperties"] is False
        assert set(s["required"]) <= set(s["properties"])
        json.dumps(t)


def test_dispatch(ingested):
    out = json.loads(agent_api.dispatch("vault_search", {"query": "insurance deductible", "k": 1}, vault=ingested))
    assert out[0]["name"] == "Auto Insurance Policy Declarations"
    written = json.loads(agent_api.dispatch("vault_write_note", {"path": "Agents/test/log", "content": "hi"}, vault=ingested))
    assert written["path"] == "Agents/test/log.md"
    assert json.loads(agent_api.dispatch("vault_upcoming_dates", {"days": 3650}, vault=ingested))
    with pytest.raises(KeyError):
        agent_api.dispatch("rm_rf", {}, vault=ingested)
    with pytest.raises(ValueError):
        agent_api.dispatch("vault_search", {}, vault=ingested)
    with pytest.raises(ValueError):
        agent_api.dispatch("vault_search", {"query": "x", "vault": "/etc"}, vault=ingested)


def test_handle_tool_uses(ingested):
    content = [
        SimpleNamespace(type="text", text="Let me check."),
        SimpleNamespace(type="tool_use", id="t1", name="vault_read_note", input={"path": "Home"}),
        {"type": "tool_use", "id": "t2", "name": "vault_read_note", "input": {"path": "Missing note"}},
    ]
    results = agent_api.handle_tool_uses(content, vault=ingested)
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert "Home" in json.loads(results[0]["content"])["content"] and "is_error" not in results[0]
    assert results[1]["is_error"] is True
