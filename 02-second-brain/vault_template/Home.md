---
title: Home
type: moc
tags:
  - moc
---
# Home

Your second brain: business and life admin in one place. Drop files into **00 Inbox**, run `python -m second_brain ingest`, and they get filed below with summaries, parties and key dates.

## Business
- [[Contracts]] - service agreements, NDAs, SOWs
- [[Clients]] - client folders, proposals, meeting notes

## Life Admin
- [[Insurance]] - policies, renewals, claims
- [[Housing]] - lease, mortgage, utilities
- [[Health]] · [[Vehicles]]

## Money
- [[Finance]] - invoices, receipts, tax, bank statements

## Thinking
- [[Notes]] - ideas, research, meeting notes ([[Unsorted]] for anything the ingester couldn't place)
- `Daily/` - daily notes and agent briefings
- `Weekly/` - weekly reviews
- `Content/` - drafts and published content
- [[Agents]] - what your AI agents read and write

## Upcoming dates
Run `python -m second_brain reminders --days 60` (or ask an agent with the `vault_upcoming_dates` tool).
Any frontmatter property ending in `_date` (e.g. `renewal_date`, `expiry_date`, `notice_deadline_date`, `due_date`) is tracked.
