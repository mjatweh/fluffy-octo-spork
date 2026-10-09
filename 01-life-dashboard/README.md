# Life Dashboard

One page that pulls your **calendar, email, tasks and connected tools** onto one dashboard and,
every morning, has Claude write a **daily briefing** about the day ahead.

```
connectors (ICS, IMAP, Outlook / Microsoft 365, tasks file, Todoist, sample data)
      │  fetch
      ▼
normalize (sort, dedupe, conflicts, "needs reply", overdue)
      │
      ▼
briefing (Claude → structured JSON; offline template as fallback)
      │
      ▼
output/dashboard.html  +  output/briefing.md  (+ <vault>/Daily/YYYY-MM-DD.md)
```

The dashboard is a single self-contained HTML file with no external assets. It is responsive, follows
your system's light/dark setting (there's also a toggle button), and has five panels:
**Briefing**, **Today's schedule** (conflicts flagged, current meeting highlighted),
**Inbox highlights** (emails that need a reply come first), **Tasks** (overdue, then due today,
then by priority) and **Connected tools** (health, item count and latency per source, plus your quick links).

## Quick start (no keys, no network)

```bash
cd 01-life-dashboard
pip install -r requirements.txt
python -m life_dashboard build --dry-run     # bundled sample data + template briefing
python -m life_dashboard serve               # http://127.0.0.1:8000/dashboard.html
```

`--dry-run` makes no network calls: data comes from `sample_data/`, which is shifted onto today's
date, and the briefing comes from a deterministic template.

## Setup with your real data

```bash
cp config.example.toml config.toml   # choose which connectors are enabled
cp .env.example .env                 # ANTHROPIC_API_KEY, IMAP_PASSWORD, TODOIST_API_TOKEN ...
python -m life_dashboard sources     # check what's enabled
python -m life_dashboard build
```

| Command | What it does |
|---|---|
| `build` | Collect, brief, write `output/dashboard.html`, `output/briefing.md` and `output/briefing-YYYY-MM-DD.md`, and print the briefing. Flags: `--dry-run`, `--sample`, `--date YYYY-MM-DD`, `--output DIR`, `-q`, `--notify` (also send a compact briefing to Telegram, or to `NOTIFY_WEBHOOK_URL`). |
| `serve` | Serve the output folder with `http.server`. Flags: `--port`, `--host`, `--build` (rebuild first), `--dry-run`. |
| `schedule` | Print a snippet that runs `build` every morning: `--format cron\|launchd\|systemd\|github`, `--time 07:00`. |
| `sources` | List the enabled connectors and every available connector type. |
| `telegram` | Find your Telegram chat id (after you've messaged your bot) and send a test message. |
| `bot` | Answer questions you send your Telegram bot ("what's on tomorrow?", "any Oculi emails to answer?") using Claude with read-only access to your calendars, inboxes, tasks and the Second Brain vault. Replies only to `TELEGRAM_CHAT_ID`. Runs until stopped; `--once` answers waiting messages and exits. The setup wizard installs it as a LaunchAgent that restarts it if it crashes. |
| `mirror` | Copy an iCloud calendar (default: the first `icloud`/`caldav` connector) into a separate Google calendar, "<name> (copy)", for the next 60 days, so the Claude app, which reads Google Calendar, can see it. `mirror auth` signs in to Google once (permission: only calendars this app creates). One-way and idempotent; the setup wizard's `google` step sets it up and runs it every 30 minutes. |
| `auth` | One-time browser sign-in for Outlook / Microsoft 365 mail and calendar. |

Global flags: `-c/--config PATH` (default `./config.toml`, then `$LIFE_DASHBOARD_CONFIG`, then the
project folder) and `-v` for verbose logging. With no config file at all, the bundled sample connectors are used.

### Configuration (`config.toml`)

TOML, read with the stdlib `tomllib`. See `config.example.toml` for a fully commented version.

```toml
timezone = "America/New_York"
output_dir = "output"
vault_path = "~/SecondBrain"          # optional, see "Second Brain" below

[llm]
model = "claude-opus-5-5"             # env CLAUDE_MODEL overrides

[[connectors]]
type = "ics"
name = "Work calendar"
source = "https://calendar.google.com/calendar/ical/.../basic.ics"

[[connectors]]
type = "imap"
name = "Gmail"
host = "imap.gmail.com"
username = "you@gmail.com"
password_env = "IMAP_PASSWORD"         # secrets live in env/.env, never in the TOML

[[links]]
name = "GitHub"
url = "https://github.com/notifications"
```

Every connector accepts `name` and `enabled = false`. If a source fails (bad password, network
down) it shows red in **Connected tools**, Claude is told it's unavailable, and the rest of the dashboard still builds.

### Built-in connectors

| `type` | Kind | Options | Notes |
|---|---|---|---|
| `ics` | calendar | `source` (path, `https://` or `webcal://`) | Google, Outlook and iCloud all publish a private iCal URL, so no OAuth is needed. Handles TZID/UTC/floating times, all-day and multi-day events, RRULE (DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, BYDAY, UNTIL, COUNT), EXDATE, RECURRENCE-ID overrides and cancelled events. |
| *(any email connector)* | email | `group`, `work_reply_from`, `work_domains`, `work_senders`, `fyi_domains`, `fyi_senders` | See "Inbox groups and work routing" below. |
| `imap` | email | `host`, `username`, `password_env`, `mailbox`, `days`, `unread_only`, `limit`, `port` | Stdlib `imaplib`, read-only (`BODY.PEEK`, so nothing gets marked as read). For Gmail, use an App Password. |
| `outlook` | email | `client_id` (or `client_id_env`), `tenant`, `folder`, `days`, `unread_only`, `limit`, `token_cache` | Outlook.com and Microsoft 365 through Microsoft Graph. Microsoft no longer accepts app passwords over IMAP, so this signs in once in the browser (see below). Read-only (`Mail.Read`). |
| `outlook_calendar` | calendar | same sign-in options as `outlook`, plus `calendar_id` | Your Microsoft 365 / Outlook.com calendar through Graph, with Teams **Join** links. Shares the `outlook` sign-in when both have the same `account`. Read-only (`Calendars.Read`). |
| `icloud` | calendar | `username` (Apple ID), `password_env` (app-specific password), `calendars` (names; default all) | iCloud over CalDAV. Sees every calendar your Apple ID can see, including calendars other people share with you, so nothing has to be made public. Read-only. |
| `caldav` | calendar | `server`, `username`, `password_env`, `calendars` | Any other CalDAV server (Fastmail, Nextcloud...). `icloud` is this with the iCloud server filled in. |
| `tasks_file` | tasks | `path` (`.md` or `.json`) | Markdown checklists, including Obsidian Tasks syntax (see below). |
| `todoist` | tasks | `token_env`, `filter` (default `today \| overdue`), `api_url` | Stdlib `urllib` against the Todoist API. |
| `sample_calendar`, `sample_email`, `sample_tasks` | — | — | Bundled demo data. |

Markdown task syntax:

```markdown
- [ ] Send invoice to ACME due:2026-10-03 !high #work
- [ ] Renew passport 📅 2026-10-10 ⏫
- [x] Completed items are skipped
```

Priority comes from `!urgent|!high|!normal|!low` (or `!p1`–`!p4`) or from the Tasks emoji
`🔺 ⏫ 🔼 🔽 ⏬`. The due date comes from `due:YYYY-MM-DD` or `📅 YYYY-MM-DD`, and the project from the first `#tag`.

### Inbox groups and work routing

Every email connector accepts these extra options:

| Option | Effect |
|---|---|
| `group` | The section the inbox appears under on the dashboard and in the briefing, e.g. `"Work"`, `"Client"`, `"Personal"`. Defaults to the connector name. Sections follow the order of the connectors in your config, and `max_emails` applies to each section. |
| `work_reply_from` | For a personal inbox that still receives work mail: the address work should come from. |
| `fyi_domains`, `fyi_senders` | Senders you're only copied on for visibility. Their mail goes into a one-line **FYI** digest instead of the reply list, unless it's addressed to you directly (you're in To, not just Cc) and asks something. The To/Cc check works for IMAP inboxes; for other sources FYI mail never counts as needing a reply. |
| `work_domains`, `work_senders` | Senders whose mail in that inbox counts as work. It gets a **work** pill and a "Reply from …" nudge, so people learn your work address. Claude also points out other mail that's clearly work. |

```toml
[[connectors]]
type = "imap"
name = "Personal Gmail"
group = "Personal"
host = "imap.gmail.com"
username = "you@gmail.com"
password_env = "GMAIL_APP_PASSWORD"
work_reply_from = "you@company.com"
work_domains = ["company.com", "bigclient.com"]
fyi_domains = ["subsidiary.com"]        # copied for visibility: FYI digest, not the reply list
```

### Outlook / Microsoft 365 email and calendar

Outlook needs a free app registration (about 3 minutes, once) so Microsoft knows which app is asking:

1. Go to https://entra.microsoft.com → **Applications → App registrations → New registration**
   (or https://portal.azure.com → App registrations). Any name works, e.g. "Life Dashboard".
2. **Supported account types:** "Accounts in any organizational directory and personal Microsoft accounts".
   Leave the redirect URI empty. Click **Register** and copy the **Application (client) ID**.
3. **Authentication → Advanced settings → Allow public client flows → Yes**, then **Save**.
4. **API permissions** should list `Microsoft Graph → User.Read`. Add **Mail.Read** and **Calendars.Read** (both Delegated). On a
   work account your admin may need to grant consent.

Then add the connectors and sign in once. Giving both the same `account` means one sign-in covers mail and calendar:

```toml
[[connectors]]
type = "outlook"
name = "Outlook"
account = "work"
client_id_env = "OUTLOOK_CLIENT_ID"   # the Application (client) ID, kept in .env
tenant = "common"                     # "consumers" = personal only, "organizations" = work/school only

[[connectors]]
type = "outlook_calendar"
name = "Outlook Calendar"
account = "work"
client_id_env = "OUTLOOK_CLIENT_ID"
```

```bash
python -m life_dashboard auth          # prints a link and a code: open it, enter the code, sign in
```

The refresh token is saved to `~/.config/life-dashboard/outlook-<account>.json` (readable only by you) and renewed
on every build, so the morning cron job needs no browser. If it ever expires (for example after a password
change), the dashboard shows the Outlook source in red and tells you to run `auth` again.

### iCloud calendars (including ones shared with you)

1. At https://account.apple.com → **Sign-In and Security → App-Specific Passwords**, create one
   (e.g. "Life Dashboard") and put it in `.env` as `ICLOUD_APP_PASSWORD`.
2. Add the connector with your Apple ID email and the calendar names you want:

```toml
[[connectors]]
type = "icloud"
name = "iCloud"
username = "you@icloud.com"
password_env = "ICLOUD_APP_PASSWORD"
calendars = ["Family"]     # omit to include every calendar
```

If a name doesn't match, the Connected tools panel lists the calendar names it found. Calendars someone else owns
and shared with you appear here too, so the owner doesn't have to make them public.

**Google Calendar / Gmail via OAuth (optional extension):** the ICS + IMAP connectors cover both
without extra dependencies. If you want the Google APIs themselves (for push, labels or multiple
calendars), write a connector that uses `google-api-python-client` + `google-auth-oauthlib`, store the
token file outside the repo, and register it as shown below. That's around 40 lines, and it's left out
here so the project doesn't need heavy dependencies.

## The briefing (Claude)

`life_dashboard/briefing.py` sends the normalized day (events, emails, open tasks, failed sources)
to Claude through the official `anthropic` SDK:

- Model: `claude-opus-5-5` by default. Override it with the `CLAUDE_MODEL` env var or `[llm] model`.
- Structured output (`output_config.format` with a JSON schema) returns `headline`, `summary`,
  `top_priorities`, `schedule_highlights`, `emails_to_reply`, `risks` and `focus_tip`. The same
  structure renders both the HTML panel and the markdown.
- Effort is set to `medium` (a short task like this doesn't need more).
- Server-side refusal fallback (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`) is
  enabled on models that support it.
- Email content is marked as untrusted data in the system prompt, as a guard against prompt injection.
- **It never breaks the morning run.** If there's no `ANTHROPIC_API_KEY`, or on an API/network
  error, a refusal or truncated output, the deterministic template briefing is used and the
  reason is shown in the page footer and on stderr.

## Run it automatically every morning

The generated snippets run `build --notify`, so the briefing also lands on your phone once Telegram is set up:

1. In Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot` and follow the prompts.
2. Put the token in `.env` as `TELEGRAM_BOT_TOKEN=...`, then send your new bot any message.
3. Run `python -m life_dashboard telegram`: it prints the `TELEGRAM_CHAT_ID=...` line to add to `.env` and sends a test message.

Without Telegram, `--notify` uses `NOTIFY_WEBHOOK_URL` (Slack / Discord), or just prints a warning.

Generate a snippet with your real paths:

```bash
python -m life_dashboard schedule --time 07:00                    # cron (Linux)
python -m life_dashboard schedule --time 07:00 --format launchd   # macOS
python -m life_dashboard schedule --time 07:00 --format systemd   # systemd user timer
python -m life_dashboard schedule --time 07:00 --format github    # GitHub Actions workflow
```

- **cron:** see `cron.example`. Run `crontab -e` and paste the line. `CRON_TZ` is set from your config
  timezone (supported by cronie and most Linux crons). Output is logged to `output/build.log`.
- **launchd (macOS):** save the plist to `~/Library/LaunchAgents/com.life-dashboard.daily.plist` and
  run `launchctl load` on it. If the Mac was asleep at 07:00, launchd runs the job at wake.
- **systemd:** a `.service` + `.timer` pair with `Persistent=true`, so a missed run catches up at boot.
- **GitHub Actions:** a workflow (cron is converted to UTC for you) that builds the dashboard and uploads
  `output/` as an artifact. Add `ANTHROPIC_API_KEY` (and any connector secrets) as repository secrets.

`.env` in the project folder (or the current directory) is loaded automatically, so cron jobs
get your keys without extra shell setup. Real environment variables always win.

## Second Brain integration

Set `vault_path` (for example the Obsidian vault from project `02`) and every build also writes
`<vault>/Daily/YYYY-MM-DD.md`. Only the block between `<!-- life-dashboard:start -->` and
`<!-- life-dashboard:end -->` is managed, so your journal lines (or other tools' content) in the same
daily note are preserved, and re-running replaces the block instead of duplicating it. New notes get
`date` / `tags: [daily, briefing]` frontmatter. Tip: point a `tasks_file` connector at a todo note inside the vault.

## Adding a connector

```python
# life_dashboard/connectors/github_prs.py
from datetime import date
from ..models import Task
from .base import Connector, register

@register
class GitHubReviews(Connector):
    type = "github_reviews"   # value of `type =` in config.toml
    kind = "tasks"            # "calendar" -> Event, "email" -> Email, "tasks" -> Task

    def fetch(self, day: date) -> list[Task]:
        token = self.secret("token")               # reads env var named by `token_env`
        repo = self.option("repo", required=True)  # raises a friendly ConnectorError
        ...                                        # self.read_text(url_or_path) is available too
        return [Task(title="Review #42", due=day, priority=2, source=self.name)]
```

Then import the module in `life_dashboard/connectors/__init__.py` and add a
`[[connectors]] type = "github_reviews"` block to your config. Exceptions raised in `fetch`
are caught and shown in the status panel. Add a test that feeds the parser a canned payload,
as `tests/test_connectors.py` does for Todoist and IMAP.

## Layout

```
01-life-dashboard/
├── life_dashboard/
│   ├── cli.py            # argparse commands, .env loader
│   ├── config.py         # TOML config, defaults, sample-connector fallback
│   ├── models.py         # Event / Email / Task / SourceStatus / Briefing / DayData
│   ├── connectors/       # base.py (interface + registry), caldav (+ iCloud), ics, imap, outlook (mail + calendar), tasks_file, todoist, sample
│   ├── normalize.py      # sorting, dedupe, conflicts, needs-reply, overdue
│   ├── briefing.py       # Claude call + offline template
│   ├── render.py         # HTML (Jinja2), markdown, Obsidian daily note
│   ├── schedule.py       # cron / launchd / systemd / GitHub Actions snippets
│   ├── pipeline.py       # collect → normalize → brief → render
│   └── templates/dashboard.html.j2
├── sample_data/          # calendar.ics, emails.json, tasks.json, tasks.md
├── tests/                # pytest; no network or API key needed (LLM client mocked)
├── config.example.toml  .env.example  cron.example  requirements.txt  pyproject.toml
```

## Tests

```bash
python -m pytest -q
```

The tests cover the connectors (sample data, the ICS edge cases, Markdown/JSON tasks, IMAP message
parsing, Outlook sign-in / token refresh / Graph mail and calendar parsing, CalDAV discovery and iCloud shared calendars, the Todoist payload), normalization, HTML/markdown/vault rendering (including HTML escaping
of email content), the briefing step with a mocked Anthropic client (request shape, refusal / error
fallback), config loading, the schedule snippets and an end-to-end `build --dry-run`.
