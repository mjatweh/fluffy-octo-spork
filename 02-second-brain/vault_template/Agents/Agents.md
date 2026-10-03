---
title: Agents
type: moc
tags:
  - moc
  - agents
---
# Agents

AI agents connect to this vault through the `second_brain` Python API, Claude tool definitions, or the MCP server.

## Folder contract
| Folder | Who writes | File naming |
|---|---|---|
| `Daily/` | executive-assistant agents, you | `YYYY-MM-DD.md` (append a `## <Agent> briefing` section; don't overwrite your own notes) |
| `Weekly/` | review/dashboard agents, you | `YYYY-Www.md` (ISO week, e.g. `2026-W40.md`) |
| `Content/` | content agents | `Content/<Drafts or Published>/<slug>.md` |
| `Agents/<agent-name>/` | each agent, its own logs/state/reports | free-form |

Agent-written notes should include frontmatter `source: <agent-name>` and `created: YYYY-MM-DD`.
Everything else (`Business/`, `Life Admin/`, `Finance/`, `Attachments/`) is owned by the ingester and you - agents should read it, not rewrite it.

Back to [[Home]]
