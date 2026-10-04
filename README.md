# fluffy-octo-spork — five AI projects for running your business and life

Each folder is a standalone Python 3.11 project with its own README, tests and `--dry-run`
mode (bundled sample data, no API key needed). With `ANTHROPIC_API_KEY` set they call Claude
(default model `claude-opus-5-5`, override with `CLAUDE_MODEL`).

| # | Project | What it does | Try it |
|---|---------|--------------|--------|
| 1 | [`01-life-dashboard`](01-life-dashboard/) | One page with your calendar, email, tasks and connected tools, plus a Claude-written daily briefing; rebuilt every morning by cron/launchd/GitHub Actions | `python -m life_dashboard build --dry-run` |
| 2 | [`02-second-brain`](02-second-brain/) | Obsidian vault + ingest of contracts, leases, insurance, notes and PDFs into linked notes; search, Q&A with citations, renewal reminders; agent API and MCP server | `python -m second_brain ingest sample_inbox --dry-run --vault /tmp/vault` |
| 3 | [`03-executive-assistant`](03-executive-assistant/) | Morning check-in and evening review every day; weekly rollup of what to keep / stop / start | `python -m exec_assistant seed-demo && python -m exec_assistant weekly --dry-run` |
| 4 | [`04-content-marketing-agent`](04-content-marketing-agent/) | Knows your brand and ICP; writes social posts, newsletters, landing pages, ads, content calendars; reviews drafts for brand voice | `python -m content_agent generate linkedin --topic "AI for small firms" --dry-run` |
| 5 | [`05-ai-workforce`](05-ai-workforce/) | A team of specialist agents led by an AI chief of staff that plans, delegates in parallel, reviews and reports, with approval gates for side effects. Includes a deal analyst (screening memos, pipeline tracker, investor one-pagers) and a trading analyst (analysis only, never trades) | `python -m workforce run "Plan next week's content and outreach" --dry-run` |

Run each command from inside its project folder.

## Setup

```bash
pip install anthropic jinja2 pytest        # mcp and pypdf are optional extras for project 2
```

### Connect your accounts once, for all five projects

Two files at the repo root hold everything; both are gitignored, so your credentials never get committed:

```bash
cp .env.example .env                              # API key, app passwords, vault path, webhook
cp connections.example.toml connections.toml      # which calendars / inboxes / task lists to read
```

- **`.env`**: every project loads it automatically. A project's own `.env` or a real environment variable wins over it.
- **`connections.toml`**: the Life Dashboard finds it automatically. The Executive Assistant and AI Workforce reach the same data through the dashboard and the vault's `Daily/` note.
- **Notifications**: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` once and the morning briefing (`build --notify`), check-in nudges, weekly reports and agent messages all reach your phone. `NOTIFY_WEBHOOK_URL` (Slack / Discord) works instead; the per-project `EA_WEBHOOK_URL` and `WORKFORCE_WEBHOOK_URL` still override it.

Where to get each credential:

| What | Link |
|---|---|
| Claude API key | https://console.anthropic.com/settings/keys |
| Google Calendar iCal link | https://calendar.google.com/calendar/r/settings → pick the calendar → "Secret address in iCal format" |
| Gmail app password (needs 2-Step Verification) | https://myaccount.google.com/apppasswords |
| Outlook calendar ICS link | https://outlook.live.com/calendar/0/options/calendar/SharedCalendars (work account: https://outlook.office.com/calendar/options/calendar/SharedCalendars) |
| iCloud app-specific password (iCloud Mail, and iCloud calendars including ones shared with you) | https://account.apple.com → Sign-In and Security → App-Specific Passwords |
| Outlook / Microsoft 365 email + calendar: app registration (one time, then `python -m life_dashboard auth`) | https://entra.microsoft.com → App registrations. Steps in [`01-life-dashboard/README.md`](01-life-dashboard/README.md#outlook--microsoft-365-email-and-calendar) |
| Todoist API token | https://app.todoist.com/app/settings/integrations/developer |
| Telegram bot (notifications) | In Telegram, message [@BotFather](https://t.me/BotFather) → `/newbot`; put the token in `.env`, message your bot once, then run `python -m life_dashboard telegram` to get your chat id and a test message |
| Quiver Quant API key (trading analyst's politician / insider / 13F signals) | https://www.quiverquant.com |
| Slack incoming webhook | https://api.slack.com/messaging/webhooks |

Outlook.com and Microsoft 365 email and calendar use Microsoft's sign-in instead of a password, because Microsoft no longer accepts app passwords. You register a free app once, then sign in once in the browser; the saved sign-in keeps scheduled runs working.

Run all tests:

```bash
for d in 0*/; do (cd "$d" && python -m pytest -q); done
```

## How they fit together

```
                 ┌──────────────────────────────┐
                 │ 5. AI Workforce              │
                 │ Chief of Staff → specialists │
                 └──────┬───────────────┬───────┘
         run_sibling    │               │ search / read / write notes
   ┌─────────────┬──────┴──────┐        │
   ▼             ▼             ▼        ▼
1. Dashboard  3. Exec Asst  4. Content  2. Second Brain (Obsidian vault at $VAULT_PATH)
   │             │             │          ▲
   └─ Daily/ ────┴─ Daily/, ───┴─ Content/Drafts/ ┘
                    Weekly/
```

The vault built by project 2 (copy `02-second-brain/vault_template`, or run
`python -m second_brain init`) is the shared memory. When `VAULT_PATH` is set:

- the Life Dashboard and the Executive Assistant write marked sections into `Daily/YYYY-MM-DD.md`
  without overwriting each other's content;
- the Executive Assistant writes weekly reviews to `Weekly/YYYY-Www.md`;
- the Content Agent saves drafts to `Content/Drafts/<type>/`;
- the AI Workforce saves run reports to `Agents/` and searches the vault through the Second Brain API.
