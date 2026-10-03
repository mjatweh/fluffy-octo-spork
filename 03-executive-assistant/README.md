# Executive Assistant Agent

An executive assistant that checks in with you **every morning and every night** to review what did
and didn't go well, and **every week** rolls that up into an analysis of what to improve next week.

- **Morning check-in** - asks for your top 3 priorities, energy (1-10), meeting load and blockers.
  It reminds you of last night's reflection and offers to carry over unfinished priorities, then Claude
  writes a short brief for the day.
- **Evening review** - goes through each priority (done / partial / not done), extra work, wins, what
  didn't go well and why, root-cause tags, energy, mood and one lesson. Claude writes a short reflection
  with 1-2 suggestions for tomorrow. Root causes are also tagged automatically from what you write
  (`meetings`, `interruptions`, `low-energy`, `scope`, `dependencies`, `overcommitment`, ...).
- **Weekly rollup** - Python computes the stats for the last 7 days: completion rate, energy average and
  trend (least-squares slope), mood, missed check-ins, recurring root causes, best and toughest day,
  priorities that keep carrying over, and patterns such as *"Completion was 33% on meeting-heavy days vs
  92% on lighter days"*. Claude then writes **Keep / Stop / Start**, **3 concrete improvements** and a
  **proposed focus for the new week**. The report goes to stdout and to a markdown file.
- **History / stats**, **cron scheduling**, **desktop and webhook nudges**, and **Obsidian vault** output.

Everything runs offline: use `--dry-run` (or leave `ANTHROPIC_API_KEY` unset) and you get deterministic
templated responses. If the API is unreachable, the check-in is still saved with a templated reply.

## Setup

```bash
cd 03-executive-assistant
pip install -r requirements.txt        # anthropic is only needed for live Claude calls
cp .env.example .env                   # then fill in ANTHROPIC_API_KEY, VAULT_PATH, ...
python -m exec_assistant seed-demo     # optional: one week of sample data
python -m exec_assistant weekly --dry-run
```

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | - | Claude API key. If unset, runs in dry-run mode. |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Model override (also `--model`). |
| `EA_DATA_DIR` | `~/.exec_assistant` | SQLite DB (`exec_assistant.db`), `reports/`, `cron.log`. |
| `VAULT_PATH` | - | Obsidian vault root. Writes `Daily/YYYY-MM-DD.md` and `Weekly/YYYY-Www.md`. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | - | Send nudges and weekly reports to Telegram (long reports are split into several messages). Usually set once in the shared root `.env`. |
| `EA_WEBHOOK_URL` | `NOTIFY_WEBHOOK_URL` | Slack, Discord, or any JSON webhook for nudges and weekly reports. |

## Daily workflow

```bash
python -m exec_assistant morning          # interactive, about 1 minute
python -m exec_assistant evening          # interactive, about 2 minutes
python -m exec_assistant weekly           # Sunday: 7-day rollup -> stdout + $EA_DATA_DIR/reports/weekly-YYYY-Www.md
python -m exec_assistant history --days 14
python -m exec_assistant stats [--json]
```

Non-interactive runs (for scripts or other agents) take a JSON answers file (`-` reads stdin) or flags.
Flags override the file.

```bash
python -m exec_assistant morning --answers morning.json
python -m exec_assistant morning --priority "Ship pricing page" --priority "Hire EM" --energy 7 --meetings 3 --blockers "legal review"
python -m exec_assistant evening --done y,p,n --energy 5 --mood 6 --wins "Pricing live" \
    --went-wrong "back-to-back meetings" --tags meetings --lessons "Block focus time"
```

```jsonc
// morning.json
{"date": "2026-10-05", "priorities": ["Ship pricing page", "Hire EM", "Board deck"],
 "energy": 7, "meetings": 3, "blockers": "legal review pending"}
// evening.json  (completed: one entry per priority: y / n / p | true / false | 1 / 0.5 / 0)
{"date": "2026-10-05", "completed": ["y", "p", "n"], "extra_done": ["fixed CI"],
 "wins": ["Pricing page live"], "didnt_go_well": "meetings ran over, waiting on legal",
 "root_causes": ["meetings"], "energy": 5, "mood": 6, "lessons": "Say no earlier"}
```

`--date YYYY-MM-DD` backdates a check-in. Running the same check-in again for a date replaces it.
For an evening review with no morning check-in, pass `"priorities"` (or `--planned "a; b"`).

## Scheduling and notifications

```bash
python -m exec_assistant schedule                     # prints crontab lines (defaults 08:00 / 21:00 / Sun 18:00)
python -m exec_assistant schedule --morning 07:30 --evening 20:45 --weekly "Fri 17:00"
```

The morning and evening cron jobs run `nudge morning|evening`. A nudge prints the reminder, shows a
desktop notification (`notify-send` on Linux, `osascript` on macOS), messages you on Telegram when it's configured, and POSTs to `EA_WEBHOOK_URL`. The
message includes the command to run. The weekly cron job runs `weekly --notify`, which builds the report
without any input and sends it to the webhook. If you'd rather review the week yourself, use
`nudge weekly` instead.

Webhook payloads use the stdlib `urllib`, shaped per service: Discord `{"content"}`, Slack `{"text"}`,
Telegram (`https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>`) `{"text"}`. Any other URL
gets both keys.

## Second Brain (Obsidian vault) integration

With `VAULT_PATH` set:

- Morning and evening entries go into `<vault>/Daily/YYYY-MM-DD.md` as `## Morning check-in` and
  `## Evening review` sections, with checkboxes for priorities and `#tags` for root causes.
- The weekly rollup goes into `<vault>/Weekly/YYYY-Www.md` (ISO week of the window's last day).

Each section is wrapped in HTML comment markers:

```markdown
<!-- exec-assistant:morning:start -->
## Morning check-in
...
<!-- exec-assistant:morning:end -->
```

Only the content between our own markers is ever replaced. Everything else in the note stays exactly
as it was: front-matter, the Life Dashboard briefing, your own notes. If the note doesn't exist it is
created with a `# YYYY-MM-DD` title. Use `--no-vault` to skip vault writes for a single run.

## Architecture

```
exec_assistant/
  cli.py       argparse commands (morning, evening, weekly, history, stats, schedule, nudge, seed-demo)
  checkins.py  question flows, answer normalization, root-cause auto-tagging, persistence
  weekly.py    7-day stats, pattern detection, markdown rendering, report output
  prompts.py   Claude prompts + deterministic dry-run templates
  llm.py       Anthropic SDK wrapper: dry-run, offline fallback, refusal handling
  store.py     sqlite3: checkins, priorities (done 0/0.5/1), tags, weekly_reports
  vault.py     marker-based section upsert for Obsidian notes
  notify.py    desktop, Telegram + webhook notifications
  demo.py      deterministic sample week
  config.py    env / .env configuration
```

Claude calls go through `client.beta.messages.create` with `output_config.effort="medium"` and
server-side refusal fallback (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`) for
models that support it. Other models use plain `messages.create`. The weekly stats are always
computed in Python and passed to Claude as authoritative numbers, so the narrative can't get the
math wrong.

## Tests

```bash
python -m pytest -q
```

Tests need no network access and no API key. The Claude client is mocked. They cover store CRUD,
scripted morning and evening conversations, weekly aggregation math on a seeded week, vault section
upserts that leave other content alone, and an end-to-end CLI run (`--answers` x 7 days, then
`weekly --dry-run`).
