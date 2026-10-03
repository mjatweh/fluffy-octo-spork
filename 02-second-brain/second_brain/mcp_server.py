"""MCP server exposing the vault to Claude Desktop / Claude Code (stdio transport).

Requires the optional `mcp` package (pip install mcp).
"""
from __future__ import annotations

import sys

from . import agent_api, config


def build_server(vault=None):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        return None
    v = str(config.vault_path(vault))
    server = FastMCP("second-brain", instructions=(
        "Tools for the user's Obsidian second brain: search and read their contracts, leases, insurance, "
        "finance and notes; check upcoming renewals/deadlines; write notes into Daily/, Weekly/, Content/ "
        "or Agents/<agent-name>/. Cite notes as [[Note Name]]."))
    docs = {t["name"]: t["description"] for t in agent_api.TOOLS}

    @server.tool(name="vault_search", description=docs["vault_search"])
    def vault_search(query: str, k: int = 5) -> list[dict]:
        return agent_api.search(query, k, vault=v)

    @server.tool(name="vault_read_note", description=docs["vault_read_note"])
    def vault_read_note(path: str) -> dict:
        return agent_api.read_note(path, vault=v)

    @server.tool(name="vault_write_note", description=docs["vault_write_note"])
    def vault_write_note(path: str, content: str, mode: str = "overwrite") -> dict:
        return agent_api.write_note(path, content, mode, vault=v)

    @server.tool(name="vault_upcoming_dates", description=docs["vault_upcoming_dates"])
    def vault_upcoming_dates(days: int = 30, include_overdue: bool = False) -> list[dict]:
        return agent_api.upcoming_dates(days, include_overdue, vault=v)

    @server.tool(name="vault_list_notes", description=docs["vault_list_notes"])
    def vault_list_notes(folder: str = "") -> list[dict]:
        return agent_api.list_notes(folder, vault=v)

    return server


def main(vault=None) -> int:
    server = build_server(vault)
    if server is None:
        print("The MCP server needs the optional 'mcp' package:  pip install mcp", file=sys.stderr)
        return 1
    print(f"second-brain MCP server on stdio (vault: {config.vault_path(vault)})", file=sys.stderr)
    server.run()  # stdio
    return 0
