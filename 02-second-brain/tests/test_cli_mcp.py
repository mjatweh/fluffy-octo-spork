import asyncio
import json

import pytest

from second_brain.cli import main


def test_cli_end_to_end(tmp_path, inbox, capsys):
    v = str(tmp_path / "v")
    assert main(["init", "--vault", v]) == 0
    assert main(["ingest", str(inbox), "--vault", v, "--dry-run", "--json"]) == 0
    out = capsys.readouterr().out
    results = json.loads(out[out.index("["):])
    assert len(results) == 6 and all(r["status"] == "ingested" for r in results)
    assert main(["index", "--vault", v, "--force"]) == 0
    capsys.readouterr()
    assert main(["search", "lease", "--vault", v, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "Residential Lease Agreement"
    assert main(["reminders", "--vault", v, "--days", "60", "--today", "2026-10-03", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert main(["ask", "when does my lease renew?", "--vault", v]) == 0
    assert "2027-03-01" in capsys.readouterr().out
    assert main(["tools"]) == 0
    assert "vault_search" in capsys.readouterr().out


def test_cli_missing_vault(tmp_path):
    assert main(["search", "x", "--vault", str(tmp_path / "nope")]) == 2


def test_mcp_server_tools(ingested):
    pytest.importorskip("mcp")
    from second_brain.mcp_server import build_server

    server = build_server(ingested)
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"vault_search", "vault_read_note", "vault_write_note",
                                       "vault_upcoming_dates", "vault_list_notes"}
    result = asyncio.run(server.call_tool("vault_search", {"query": "lease renewal", "k": 1}))
    assert "Residential Lease Agreement" in str(result)
