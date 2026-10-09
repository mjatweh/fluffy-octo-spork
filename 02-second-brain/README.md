# 02 · Second Brain

> Drop all your business and life admin into one folder (contracts, leases, insurance, notes, PDFs, all of it). Build your second brain in Obsidian, then connect it to your AI agents.

`second_brain` turns a drop folder of mixed files into an **Obsidian vault**. Each file gets a note with YAML frontmatter, a summary, parties, important dates and amounts. You can search the vault locally, **ask** questions and get answers with note citations, list upcoming **renewals and deadlines**, and expose all of it to AI agents as a **Python API**, **Claude tool definitions**, or an **MCP server**.

Everything works **offline with no API key**. Deterministic heuristics stand in for Claude, and search is a pure-Python BM25 index.

## Setup

```bash
cd 02-second-brain
pip install -r requirements.txt        # all optional: anthropic, pypdf, mcp, pyyaml, pytest
cp .env.example .env                   # then export the variables (or set them in your shell)
export ANTHROPIC_API_KEY=sk-ant-...    # optional: enables Claude extraction and answers
export SECOND_BRAIN_VAULT=$PWD/vault   # optional: default is ./vault

python -m second_brain init            # copies vault_template/ to ./vault (or --vault PATH)
```

| Env var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | (unset → offline) | Claude calls |
| `CLAUDE_MODEL` | `claude-opus-5-5` | model override |
| `SECOND_BRAIN_VAULT` | `$VAULT_PATH`, else `./vault` | vault location (every command also takes `--vault`). The shared `VAULT_PATH` used by the sibling projects also works. |
| `SECOND_BRAIN_FALLBACKS` | `1` | server-side refusal fallback beta (`fallbacks="default"`). Set `0` for models or platforms that don't support it |

### Open it in Obsidian
Obsidian → **Open folder as vault** → choose your `vault/` folder. The template comes with:
- `Home.md`, the map of content (MOC) linking every area, plus a hub note per area (`[[Contracts]]`, `[[Insurance]]`, …). Ingested notes link back to their hub, so the hub's Backlinks pane lists everything in that area.
- Core plugins enabled: **Templates** (folder `Templates/`), **Daily notes** (folder `Daily/`, format `YYYY-MM-DD`, template `Templates/Daily note`), Properties, Backlinks, Graph.
- Templates: *Document note*, *Daily note*, *Weekly review*, *Meeting*.
- New attachments go to `Attachments/`.

```
vault/
├── Home.md                 ← MOC
├── 00 Inbox/               ← drop files here
├── Business/Contracts/  Business/Clients/
├── Life Admin/Insurance/  Life Admin/Housing/  Life Admin/Health/  Life Admin/Vehicles/
├── Finance/
├── Notes/  Notes/Unsorted/ ← anything the classifier couldn't place
├── Daily/  Weekly/  Content/  Agents/
├── Attachments/            ← originals (embedded in notes with ![[file]])
└── Templates/
```

## Workflow: drop → ingest → ask

```bash
# 1. Drop files into vault/00 Inbox/ (or point at any folder)
python -m second_brain ingest                       # uses <vault>/00 Inbox; originals are moved to Attachments/
python -m second_brain ingest ~/Downloads/admin     # an external folder; originals are kept (--move to delete them)
python -m second_brain ingest --dry-run             # never call Claude (deterministic heuristics)

# 2. Search / ask
python -m second_brain search lease renewal notice
python -m second_brain ask "when does my lease renew?"

# 3. What's coming up?
python -m second_brain reminders --days 60          # --json for machines, --overdue, --today YYYY-MM-DD
```

Try it on the bundled samples:
```bash
python -m second_brain init --vault /tmp/sb
python -m second_brain ingest sample_inbox --vault /tmp/sb --dry-run
python -m second_brain reminders --vault /tmp/sb --days 120 --today 2026-10-03
```

### Folders that sync to your Mac (OneDrive, Google Drive, Dropbox)
List them in `watch_folders.txt` at the repo root (gitignored; copy `watch_folders.example.txt`), one per line.
`python -m second_brain watch` files anything new from them and leaves the originals in place; already-filed
files are skipped by content hash. The setup wizard runs it daily before the morning dashboard.

### What ingest does, per file
1. **Extracts text**: txt/md/csv/json/eml, HTML, `.docx` (stdlib zip/xml), PDF (when `pypdf` is installed; otherwise the PDF is linked with a warning). Images and other binaries are linked but not read.
2. **Classifies** the file into `lease | insurance | contract | client | finance | health | vehicle | note | other` and picks the vault folder.
3. **Extracts metadata**: title, document type (`lease-agreement`, `auto-insurance`, `nda`, `invoice`…), parties, dates (`renewal_date`, `expiry_date`, `start_date`, `due_date`, `notice_deadline_date`…), amounts, tags.
   - **With an API key:** Claude (`claude-opus-5-5`) returns JSON constrained by a JSON schema (`output_config.format`). Heuristics fill in any field it leaves empty. On an API error or refusal, ingest falls back to heuristics.
   - **Offline:** regex and keyword heuristics. When a document states a notice period ("60 days' written notice"), ingest computes `notice_deadline_date` back from the end of the term.
4. **Copies the original** to `Attachments/`. A different file with the same name gets a hash suffix.
5. **Writes a note** with frontmatter, a summary callout, key details, `![[original]]`, `[[hub]]` and `[[Home]]` links, `[[Party]]` links, *Related* links to other notes that share a party, and the full extracted text in a folded callout so it's searchable.
6. **Skips files it has already ingested.** It keys on the SHA-256 of the file contents, so a renamed copy is skipped too. The hash is stored in each note's frontmatter (`source_sha256`), so there's no separate manifest to drift.

Example frontmatter:
```yaml
---
title: Residential Lease Agreement
type: lease-agreement
category: lease
tags:
  - lease
  - lease-agreement
  - renewal
parties:
  - Oakwood Property Management LLC
  - Jamie Rivera
expiry_date: 2027-02-28
notice_deadline_date: 2026-12-30
renewal_date: 2027-03-01
start_date: 2026-03-01
notice_days: 60
amounts:
  - "$2,400 per month"
source_file: "[[apartment_lease.txt]]"
source_sha256: 677bb7…
ingested: 2026-10-03
extracted_by: heuristic        # or claude
generated_by: second-brain
---
```

### Search and ask
- `index` / `search`: a BM25 index in pure Python (light stemming, title boost, frontmatter included), stored at `<vault>/.second_brain/index.json`. It refreshes incrementally by file mtime before every search, so notes that agents write show up right away. `Templates/` and `Attachments/` are not indexed.
- `ask`: retrieves the top-k notes and asks Claude to answer **only from those notes**, citing them as `[[Note Name]]`. Offline, it returns the top snippets. When the question asks about a date (renew, expire, due, notice) and the top note has that date in its frontmatter, it puts a "Likely answer" line first.

### Reminders
Any frontmatter property ending in `_date` counts as an upcoming date, except history fields (`start_date`, `signed_date`, `document_date`). So do `due`, `deadline`, `renewal`, `expiry` and `expires`. The same rule applies to notes you or other agents write by hand: add `renewal_date: 2027-01-01` to any note and it shows up.

## Connect your AI agents

### 1. Python API (`second_brain.agent_api`)
```python
from second_brain import agent_api as brain   # vault = $SECOND_BRAIN_VAULT or ./vault; every function takes vault=

brain.search("lease renewal", k=5)            # [{path, name, title, score, snippet}]
brain.read_note("Residential Lease Agreement") # path or bare note name -> {path, frontmatter, content}
brain.write_note("Daily/2026-10-04.md", "## Exec assistant briefing\n…", mode="append")  # overwrite|append|create
brain.upcoming_dates(days=30)                 # [{date, days_left, label, note, name, title, type}]
brain.list_notes("Business/Contracts")        # [{path, title, type}]
```
Every path is resolved inside the vault. `..`, absolute escapes, and dot-folders such as `.obsidian` are rejected.

### 2. Claude tool definitions
`agent_api.TOOLS` contains JSON schemas for `vault_search`, `vault_read_note`, `vault_write_note`, `vault_upcoming_dates` and `vault_list_notes`. `agent_api.dispatch(name, input)` runs one call and returns a JSON string. `agent_api.handle_tool_uses(content)` turns every `tool_use` block in a response into `tool_result` blocks for a single user message; errors come back with `is_error: true`.

```python
import anthropic
from second_brain import agent_api

client = anthropic.Anthropic()
messages = [{"role": "user", "content": "Which of my policies or contracts need action in the next 60 days?"}]
while True:
    resp = client.messages.create(model="claude-opus-5-5", max_tokens=16000,
                                  tools=agent_api.TOOLS, messages=messages)
    if resp.stop_reason != "tool_use":
        break
    messages += [{"role": "assistant", "content": resp.content},
                 {"role": "user", "content": agent_api.handle_tool_uses(resp.content)}]
print(next(b.text for b in resp.content if b.type == "text"))
```
`python -m second_brain tools` prints the schemas.

### 3. MCP server (Claude Desktop / Claude Code)
```bash
pip install mcp
python -m second_brain mcp --vault /path/to/vault      # stdio transport
```
It exposes the same five tools under the same names. Without the `mcp` package, the command prints an install hint and exits with code 1.

- **Claude Desktop:** merge `mcp_config/claude_desktop_config.json` into `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows), then fix the absolute paths.
- **Claude Code:** copy `mcp_config/.mcp.json` to your project root and fix the paths, or run:
  `claude mcp add second-brain -e PYTHONPATH=$PWD -e SECOND_BRAIN_VAULT=/path/to/vault -- python3 -m second_brain mcp`

## Folder contract for other agents
Sibling projects in this monorepo (exec assistant, dashboard, content engine…) share the vault through these folders:

| Folder | Writer | Naming / rules |
|---|---|---|
| `Daily/` | exec-assistant agents, you | `YYYY-MM-DD.md`. **Append** a section such as `## Exec assistant briefing` (`write_note(..., mode="append")`). Never overwrite your own notes. |
| `Weekly/` | review / dashboard agents, you | `YYYY-Www.md` (ISO week, e.g. `2026-W40.md`) |
| `Content/` | content agents | `Content/Drafts/<slug>.md`, `Content/Published/<slug>.md` |
| `Agents/<agent-name>/` | each agent | its own logs, state and reports, free-form |
| `Business/`, `Life Admin/`, `Finance/`, `Notes/`, `Attachments/` | **ingest** and you | agents read these, they don't rewrite them |
| `00 Inbox/` | anyone | drop files to be ingested |

Conventions for agent-written notes:
- Frontmatter should include `source: <agent-name>` and `created: YYYY-MM-DD`, plus `type:` (`daily`, `weekly`, `content`, `report`…).
- Add any deadline as a `*_date` property so it appears in `reminders`.
- Link to other notes with `[[Note Name]]`.

For reading: `agent_api.upcoming_dates(days)` / `python -m second_brain reminders --json` gives dashboards and exec assistants the renewal and deadline feed. `agent_api.search` and `read_note` give them document context.

## Tests
```bash
cd 02-second-brain && python -m pytest -q
```
The tests need no network and no API key; Claude is mocked. They cover classification and date/party/amount heuristics, frontmatter round-trips, text extraction (docx, html, PDF with or without pypdf), dry-run ingest into a temp copy of the vault (idempotency, moving files out of an in-vault inbox, attachment name collisions), Claude extraction with a mocked client, the refusal fallback, the model override, BM25 ranking, incremental indexing, offline and Claude `ask`, reminders, the agent API (including path safety and the tool dispatcher), the CLI end to end, and the MCP tool listing.

## Layout
```
second_brain/
  cli.py          argparse entry (python -m second_brain …)
  config.py       env config (model, vault path, fallbacks)
  extract.py      text extraction (txt/md/html/docx/pdf)
  classify.py     offline heuristics: category, type, parties, dates, amounts, summary
  llm.py          Claude: JSON-schema extraction + grounded answers (mock-friendly)
  ingest.py       drop folder → notes + attachments (idempotent)
  index.py        BM25 index + search
  qa.py           ask
  reminders.py    upcoming dates
  agent_api.py    Python API + Claude tool schemas + dispatcher
  mcp_server.py   MCP server (optional `mcp` dependency)
  frontmatter.py  YAML frontmatter read/write
  vault.py        path safety, note iteration, init
vault_template/   ready-to-open Obsidian vault
sample_inbox/     sample lease, insurance policy, contract, invoice, meeting note, image
mcp_config/       claude_desktop_config.json and .mcp.json snippets
```
