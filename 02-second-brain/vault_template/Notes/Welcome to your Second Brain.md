---
title: Welcome to your Second Brain
type: note
tags:
  - note
  - getting-started
---
# Welcome to your Second Brain

1. Drop contracts, leases, insurance policies, receipts, PDFs - anything - into **00 Inbox** (or any folder).
2. Run `python -m second_brain ingest` (add `--dry-run` to work offline without Claude).
3. Each file is copied to `Attachments/` and gets a note in the right folder with a summary, parties, important dates and amounts.
4. Ask questions: `python -m second_brain ask "when does my lease renew?"`
5. Connect your agents via the MCP server or `second_brain.agent_api`.

See [[Home]] and [[Agents]].
