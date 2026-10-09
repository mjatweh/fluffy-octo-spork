#!/usr/bin/env python3
"""One-command setup, health check and update for all five projects (macOS first, Linux works too).

    python3 setup_wizard.py            guided setup: asks for each account, tests it right away
    python3 setup_wizard.py --check    health check: every connection, schedule, vault and Telegram
    python3 setup_wizard.py --update   pull the latest code, refresh packages, then --check
    python3 setup_wizard.py --only telegram   re-run one step (python, claude, vault, accounts,
                                              telegram, schedule, build)

Your answers (addresses, calendar names) can be pre-filled from setup.local.toml (copy
setup.example.toml). Secrets go only into .env, which is chmod 600. setup.local.toml, .env and
connections.toml are all gitignored: nothing personal is ever committed.
"""
from __future__ import annotations

import os
import shutil
import sys

PY_CANDIDATES = ["python3.13", "python3.12", "python3.11"]
PY_DIRS = ["/opt/homebrew/bin", "/usr/local/bin", "/Library/Frameworks/Python.framework/Versions/Current/bin"]


def find_newer_python() -> str | None:
    """A Python 3.11+ on this machine, even when the `python3` you typed is older (macOS ships 3.9)."""
    for name in PY_CANDIDATES:
        for d in [None, *PY_DIRS]:
            path = shutil.which(name) if d is None else os.path.join(d, name)
            if path and os.access(path, os.X_OK):
                return path
    return None


if sys.version_info < (3, 11):  # must run before any 3.11-only import below
    _newer = find_newer_python()
    if _newer:
        os.execv(_newer, [_newer, os.path.abspath(__file__), *sys.argv[1:]])
    print(f"This needs Python 3.11 or newer; this Mac's python3 is {sys.version.split()[0]}.\n"
          "Install the latest Python (free, about 2 minutes):\n"
          "  1. Open https://www.python.org/downloads/macos/ and click the top 'Download macOS installer' link.\n"
          "  2. Open the downloaded .pkg and click Continue / Agree / Install until it says it's done.\n"
          "  3. Close Terminal, open it again, and run: cd ~/fluffy-octo-spork && python3 setup_wizard.py")
    sys.exit(1)

import argparse  # noqa: E402
import getpass  # noqa: E402
import platform  # noqa: E402
import plistlib  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import urllib.parse  # noqa: E402
import tomllib  # noqa: E402
import venv  # noqa: E402
import webbrowser  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / "bin" / "python"
DEPS = ["anthropic", "jinja2", "pypdf", "certifi"]
ENV_FILE = ROOT / ".env"
CONNECTIONS = ROOT / "connections.toml"
ANSWERS = ROOT / "setup.local.toml"
DASHBOARD = ROOT / "01-life-dashboard"
IS_MAC = platform.system() == "Darwin"
HOME = Path.home()
OBSIDIAN_ICLOUD = HOME / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
ICLOUD_DRIVE = HOME / "Library/Mobile Documents/com~apple~CloudDocs"
LAUNCH_AGENTS = HOME / "Library/LaunchAgents"
LOG_DIR = HOME / "Library/Logs/life-assistant" if IS_MAC else HOME / ".life-assistant/logs"
LABEL = "com.life-assistant"
STEPS = ["python", "claude", "vault", "accounts", "telegram", "google", "schedule", "build"]

IMAP_HOSTS = {"gmail": "imap.gmail.com", "icloud": "imap.mail.me.com", "yahoo": "imap.mail.yahoo.com"}
HELP = {
    "claude": """1. Open https://console.anthropic.com/settings/keys and sign in.
2. Click "Create Key", name it "Life Assistant", and copy the key (it starts with sk-ant-).
   (Billing must be set up under Plans & Billing for the key to work.)""",
    "gmail": """1. Open https://myaccount.google.com/apppasswords
   Check the avatar at the top right: you must be signed in as {address}.
2. If it says app passwords aren't available: turn on 2-Step Verification first at
   https://myaccount.google.com/signinoptions/twosv , then reopen the link above.
   (On a company Google Workspace account, the admin may have switched app passwords off.)
3. App name: "Life Dashboard" -> Create. Copy the 16-letter password (spaces don't matter).""",
    "icloud": """1. Open https://account.apple.com and sign in with your Apple ID.
2. Sign-In and Security -> App-Specific Passwords -> "+" -> name it "Life Dashboard".
3. Copy the password (looks like abcd-efgh-ijkl-mnop).""",
    "imap": """Create an app password for {address} in that provider's security settings.""",
    "google_ics": """1. Open https://calendar.google.com/calendar/r/settings signed in as {address}.
2. On the left, under "Settings for my calendars", click your calendar.
3. Scroll to "Integrate calendar" and copy "Secret address in iCal format".
   (If it's missing, your Workspace admin disabled it: press Enter to skip for now.)""",
    "microsoft": """One-time free app registration so Microsoft lets the dashboard read your mail and calendar:
1. Open https://entra.microsoft.com and sign in as {address}.
2. Applications -> App registrations -> New registration. Name: "Life Dashboard".
   Supported account types: "Accounts in any organizational directory and personal Microsoft accounts".
   Leave Redirect URI empty -> Register.
3. Copy the "Application (client) ID" shown on the next page.
4. Left menu: Authentication -> "Allow public client flows" -> Yes -> Save.
5. Left menu: API permissions -> Add a permission -> Microsoft Graph -> Delegated ->
   tick Mail.Read and Calendars.Read -> Add permissions.
   (If your company blocks this, its IT admin has to click "Grant admin consent".)""",
    "google": """Copy your iCloud calendar into Google Calendar so the Claude app can see it (one time, ~10 min).
In the browser page that opened (Google Cloud, signed in as {address}):
1. Top bar: "Select a project" -> New project -> name it Life Assistant -> Create, then select it.
2. Search bar: "Google Calendar API" -> Enable.
3. Search bar: "Google Auth Platform" -> Get started -> app name Life Assistant, your email ->
   Audience: External -> finish. Then left menu Audience -> "Publish app" -> Confirm
   (otherwise Google signs you out every 7 days).
4. Left menu Clients -> Create client -> Application type: Desktop app -> name Life Assistant -> Create.
5. Copy the Client ID and Client secret it shows.""",
    "telegram": """1. On your phone, open Telegram and search for @BotFather.
2. Send /newbot, pick a name (e.g. "Michael's Assistant") and a username ending in "bot".
3. BotFather replies with a token like 123456789:AA... Copy it.""",
}


# --- small, testable helpers -------------------------------------------------------------------

def read_env(path: Path | None = None) -> dict[str, str]:
    path = path or ENV_FILE
    env: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            key = key.removeprefix("export ").strip()
            if sep and key and not key.startswith("#"):
                env[key] = value.strip().strip("'\"")
    return env


def update_env(path: Path, updates: dict[str, str]) -> None:
    """Set KEY=value lines in place (keeping comments and other keys), append new keys, chmod 600."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    todo = dict(updates)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].removeprefix("export ").strip()
        if "=" in line and not line.lstrip().startswith("#") and key in todo:
            lines[i] = f"{key}={todo.pop(key)}"
    lines += [f"{k}={v}" for k, v in todo.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def render_toml(settings: dict, tables: dict[str, list[dict]]) -> str:
    out = [f"{k} = {toml_value(v)}" for k, v in settings.items() if v not in (None, "", [])]
    for name, rows in tables.items():
        for row in rows:
            out += ["", f"[[{name}]]"] + [f"{k} = {toml_value(v)}" for k, v in row.items() if v not in (None, "", [])]
    return "\n".join(out) + "\n"


def env_name(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.upper()).strip("_")


def connectors_from(answers: dict, vault: Path | None) -> list[dict]:
    """Turn the answers file's [[email]] / [[calendar]] entries into connections.toml connectors."""
    out: list[dict] = []
    for c in answers.get("calendar", []):
        p = c.get("provider")
        if p == "google" and c.get("ics_url"):
            out.append({"type": "ics", "name": c["name"], "source": c["ics_url"]})
        elif p == "outlook":
            out.append({"type": "outlook_calendar", "name": c["name"], "account": c.get("account", "outlook"),
                        "client_id_env": "OUTLOOK_CLIENT_ID", "tenant": c.get("tenant", "common")})
        elif p == "icloud" and c.get("apple_id"):
            out.append({"type": "icloud", "name": c["name"], "username": c["apple_id"],
                        "password_env": "ICLOUD_APP_PASSWORD", "calendars": c.get("calendars", [])})
    for e in answers.get("email", []):
        p = e.get("provider", "gmail")
        extra = {k: e[k] for k in ("fyi_domains", "fyi_senders", "work_reply_from", "work_domains", "work_senders")
                 if e.get(k)}
        if p == "outlook":
            out.append({"type": "outlook", "name": e["name"], "group": e.get("group", ""),
                        "account": e.get("account", "outlook"), "client_id_env": "OUTLOOK_CLIENT_ID",
                        "tenant": e.get("tenant", "common"), **extra})
        elif e.get("address"):
            out.append({"type": "imap", "name": e["name"], "group": e.get("group", ""),
                        "host": e.get("host") or IMAP_HOSTS.get(p, ""), "username": e["address"],
                        "password_env": e.get("secret_env") or env_name(e["name"]) + "_PASSWORD", **extra})
    if vault:
        out.append({"type": "tasks_file", "name": "Todo", "path": str(vault / "Todo.md")})
    return out


def write_connections(answers: dict, vault: Path | None, path: Path | None = None) -> Path:
    path = path or CONNECTIONS
    settings = {"timezone": answers.get("timezone", ""), "output_dir": "01-life-dashboard/output",
                "max_emails": answers.get("max_emails", 8)}
    if IS_MAC and ICLOUD_DRIVE.is_dir():
        settings["publish_dir"] = str(ICLOUD_DRIVE / "Life Dashboard")
    if path.is_file():
        path.with_suffix(".toml.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text("# Written by setup_wizard.py. Re-run the wizard to change accounts.\n"
                    + render_toml(settings, {"connectors": connectors_from(answers, vault)}), encoding="utf-8")
    return path


def launchd_plist(name: str, args: list[str], workdir: Path, hour: int | None = None, minute: int | None = None,
                  weekday: int | None = None, keep_alive: bool = False, every: int | None = None) -> bytes:
    """A LaunchAgent that runs at a time of day. Unlike cron, launchd runs a missed job when the Mac wakes.
    ``keep_alive`` instead starts it at login and restarts it whenever it crashes (for the Telegram bot)."""
    if keep_alive:
        when = {"RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 30}
    elif every:
        when = {"RunAtLoad": True, "StartInterval": every}
    else:
        when = {"StartCalendarInterval": {"Hour": hour, "Minute": minute,
                                          **({"Weekday": weekday} if weekday is not None else {})}}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return plistlib.dumps({
        "Label": f"{LABEL}.{name}", "ProgramArguments": args, "WorkingDirectory": str(workdir),
        **when,
        "StandardOutPath": str(LOG_DIR / f"{name}.log"), "StandardErrorPath": str(LOG_DIR / f"{name}.log"),
        "EnvironmentVariables": {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"},
    })


def schedule_jobs(py: Path, at: str = "07:00") -> list[dict]:
    hour, minute = (int(x) for x in at.split(":"))
    ea = ROOT / "03-executive-assistant"
    return [
        {"name": "dashboard", "args": [str(py), "-m", "life_dashboard", "build", "--notify", "-q"],
         "workdir": DASHBOARD, "hour": hour, "minute": minute},
        {"name": "checkin-morning", "args": [str(py), "-m", "exec_assistant", "nudge", "morning"],
         "workdir": ea, "hour": 8, "minute": 0},
        {"name": "checkin-evening", "args": [str(py), "-m", "exec_assistant", "nudge", "evening"],
         "workdir": ea, "hour": 21, "minute": 0},
        {"name": "weekly-review", "args": [str(py), "-m", "exec_assistant", "weekly", "--notify"],
         "workdir": ea, "hour": 18, "minute": 0, "weekday": 0},
        {"name": "telegram-bot", "args": [str(py), "-m", "life_dashboard", "bot"],
         "workdir": DASHBOARD, "keep_alive": True},
        {"name": "calendar-copy", "args": [str(py), "-m", "life_dashboard", "mirror"],
         "workdir": DASHBOARD, "every": 1800},
    ]


# --- terminal UI --------------------------------------------------------------------------------

class UI:
    def say(self, text: str = "") -> None:
        print(text)

    def ask(self, prompt: str, default: str = "") -> str:
        value = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
        return value or default

    def secret(self, prompt: str) -> str:
        return getpass.getpass(f"{prompt} (hidden while you paste, then press Enter): ").strip()

    def yes(self, prompt: str, default: bool = True) -> bool:
        value = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        return default if not value else value.startswith("y")

    def choose(self, prompt: str, options: list[str]) -> int:
        for i, o in enumerate(options, 1):
            print(f"  {i}. {o}")
        while True:
            value = input(f"{prompt} [1]: ").strip() or "1"
            if value.isdigit() and 1 <= int(value) <= len(options):
                return int(value) - 1


def header(ui: UI, title: str) -> None:
    ui.say("\n" + "=" * 72 + f"\n  {title}\n" + "=" * 72)


def open_url(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


# --- connection tests (reuse the dashboard's own connectors) --------------------------------------

def dashboard_modules():
    sys.path.insert(0, str(DASHBOARD))
    from life_dashboard.config import Config
    from life_dashboard.connectors import build_connector
    return Config, build_connector


def test_connector(options: dict, tz: str) -> tuple[bool, str]:
    os.environ.update({k: v for k, v in read_env().items() if k not in os.environ or not os.environ[k]})
    Config, build_connector = dashboard_modules()
    try:
        items = build_connector(options, Config(timezone=tz, base_dir=ROOT)).fetch(date.today())
        return True, f"{len(items)} item(s) today"
    except Exception as exc:  # report every failure the same friendly way
        return False, str(exc) or type(exc).__name__


# --- steps --------------------------------------------------------------------------------------

class Wizard:
    def __init__(self, ui: UI | None = None):
        self.ui = ui or UI()
        self.env = read_env()
        self.answers = tomllib.loads(ANSWERS.read_text(encoding="utf-8")) if ANSWERS.is_file() else {}

    def save_env(self, **updates: str) -> None:
        update_env(ENV_FILE, updates)
        self.env.update(updates)
        os.environ.update(updates)

    def save_answers(self) -> None:
        tables = {k: self.answers.get(k, []) for k in ("email", "calendar")}
        settings = {k: v for k, v in self.answers.items() if k not in tables}
        ANSWERS.write_text("# Your private setup answers (gitignored). Edit and re-run the wizard.\n"
                           + render_toml(settings, tables), encoding="utf-8")

    def get_secret(self, key: str, help_key: str, **fmt) -> str | None:
        ui = self.ui
        if self.env.get(key) and ui.yes(f"{key} is already saved. Keep it?"):
            return self.env[key]
        ui.say(HELP[help_key].format(**fmt))
        value = ui.secret(f"Paste {key}").replace(" ", "") if help_key in ("gmail", "icloud") else ui.secret(f"Paste {key}")
        if not value:
            ui.say("  Skipped.")
            return None
        self.save_env(**{key: value})
        return value

    # 1
    def step_python(self) -> None:
        header(self.ui, "Step 1: Python packages")
        if not VENV_PY.exists():
            self.ui.say("Creating a private Python environment in .venv ...")
            venv.create(VENV, with_pip=True)
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "--upgrade", *DEPS], check=True)
        self.ui.say("✔ Packages installed.")

    # 2
    def step_claude(self) -> None:
        header(self.ui, "Step 2: Claude API key (writes your briefings)")
        open_url("https://console.anthropic.com/settings/keys")
        key = self.get_secret("ANTHROPIC_API_KEY", "claude")
        while key:
            ok, detail = check_claude(key)
            self.ui.say(("  ✔ " if ok else "  ✘ ") + detail)
            if ok or not self.ui.yes("Paste the key again?"):
                return
            self.env.pop("ANTHROPIC_API_KEY", None)
            key = self.get_secret("ANTHROPIC_API_KEY", "claude")

    # 3
    def step_vault(self) -> Path:
        ui = self.ui
        header(ui, "Step 3: Second Brain vault (synced to your iPhone through iCloud)")
        name = self.answers.get("vault_name", "SecondBrain")
        default = OBSIDIAN_ICLOUD / name if IS_MAC else HOME / name
        if IS_MAC and not OBSIDIAN_ICLOUD.is_dir():
            ui.say("Obsidian's iCloud folder doesn't exist yet. To create it (2 minutes):\n"
                   "  1. Install Obsidian on your iPhone (App Store) and on this Mac (https://obsidian.md).\n"
                   f"  2. On the iPhone: Create new vault -> name it \"{name}\" -> turn ON \"Store in iCloud\".\n"
                   "  3. Wait a minute for iCloud to sync it to this Mac.")
            ui.yes("Done? (press Enter to continue; I'll create a local vault if it's still missing)")
        if IS_MAC and not OBSIDIAN_ICLOUD.is_dir():
            default = HOME / name
        vault = Path(ui.ask("Vault folder", str(self.env.get("VAULT_PATH") or default))).expanduser()
        if not (vault / "Home.md").exists():
            subprocess.run([str(VENV_PY), "-m", "second_brain", "init", str(vault), "--force"],
                           cwd=ROOT / "02-second-brain", check=True)
        (vault / "Todo.md").touch()
        self.save_env(VAULT_PATH=str(vault))
        ui.say(f"✔ Vault ready at {vault}\n  Open it in Obsidian: \"Open folder as vault\" (Mac) — on iPhone it appears automatically.")
        return vault

    # 4
    def step_accounts(self) -> None:
        ui = self.ui
        header(ui, "Step 4: Email and calendars (each one is tested right away)")
        a = self.answers
        if not a.get("timezone"):
            a["timezone"] = ui.ask("Your time zone (e.g. America/New_York)", "America/New_York")
        if not a.get("email") and not a.get("calendar"):
            self.ask_accounts()
        for e in a.get("email", []):
            self.setup_email(e)
        for c in a.get("calendar", []):
            self.setup_calendar(c)
        self.save_answers()
        vault = Path(self.env["VAULT_PATH"]) if self.env.get("VAULT_PATH") else None
        ui.say(f"✔ Wrote {write_connections(a, vault)}")

    def ask_accounts(self) -> None:
        ui, a = self.ui, self.answers
        ui.say("No setup.local.toml found, so let's list your accounts.")
        while ui.yes("Add an email account?"):
            p = ["gmail", "outlook", "icloud", "imap"][ui.choose("Provider", ["Gmail / Google Workspace",
                                                               "Outlook / Microsoft 365", "iCloud Mail", "Other (IMAP)"])]
            address = ui.ask("Email address")
            entry = {"name": ui.ask("Short name", address.split("@")[-1].split(".")[0].upper() + " mail"),
                     "provider": p, "address": address, "group": ui.ask("Section on the dashboard", "Work")}
            if p == "outlook":
                entry["account"] = env_name(address.split("@")[-1].split(".")[0]).lower()
            a.setdefault("email", []).append(entry)
        while ui.yes("Add a calendar?"):
            p = ["google", "outlook", "icloud"][ui.choose("Provider", ["Google Calendar", "Outlook / Microsoft 365",
                                                                        "iCloud (incl. calendars shared with you)"])]
            entry = {"name": ui.ask("Short name", f"{p.title()} calendar"), "provider": p}
            if p == "google":
                entry["address"] = ui.ask("Google account email")
            if p == "outlook":
                entry["account"] = ui.ask("Same short account name as its email (e.g. work)", "outlook")
            if p == "icloud":
                entry["calendars"] = [c.strip() for c in ui.ask("Calendar names, comma-separated (empty = all)").split(",") if c.strip()]
            a.setdefault("calendar", []).append(entry)

    def retry_test(self, options: dict, label: str, fix, again=None) -> bool:
        while True:
            ok, detail = test_connector(options, self.answers.get("timezone", ""))
            self.ui.say(f"  {'✔' if ok else '✘'} {label}: {detail}")
            if ok:
                return True
            choice = self.ui.choose("What now?", ["Fix it (enter details again)", "Try again", "Skip for now"])
            if choice == 2:
                return False
            if choice == 0:
                fix()
            elif again:
                again()

    def setup_email(self, e: dict) -> None:
        ui, p = self.ui, e.get("provider", "gmail")
        ui.say(f"\n--- {e['name']} ({e.get('address', p)}) ---")
        if p == "outlook":
            self.microsoft_signin(e.get("account", "outlook"), e.get("address", "your Microsoft account"))
        else:
            if not e.get("address"):
                e["address"] = ui.ask("Email address")
            e.setdefault("secret_env", env_name(e["name"]) + "_PASSWORD")
            help_key = p if p in HELP else "imap"
            if p == "gmail":
                open_url("https://myaccount.google.com/apppasswords?authuser=" + urllib.parse.quote(e["address"]))
            self.get_secret(e["secret_env"], help_key, address=e["address"])
        (options,) = connectors_from({"email": [e]}, None)
        again = None
        if p == "outlook":
            def fix():
                self.microsoft_signin(e.get("account", "outlook"), e.get("address", ""), force=True)
            def again():  # repeat the sign-in when it didn't finish; keeps the saved client ID
                self.microsoft_signin(e.get("account", "outlook"), e.get("address", ""))
        else:
            def fix():
                self.env.pop(e["secret_env"], None)
                self.get_secret(e["secret_env"], p if p in HELP else "imap", address=e["address"])
        self.retry_test(options, e["name"], fix, again)

    def setup_calendar(self, c: dict) -> None:
        ui, p = self.ui, c.get("provider")
        ui.say(f"\n--- {c['name']} ---")
        if p == "google":
            def ask_link():
                ui.say(HELP["google_ics"].format(address=c.get("address", "your Google account")))
                open_url("https://calendar.google.com/calendar/r/settings")
                c["ics_url"] = ui.ask("Paste the secret iCal address", c.get("ics_url", ""))
            if not c.get("ics_url"):
                ask_link()
            if not c.get("ics_url"):
                return
            fix = ask_link
        elif p == "icloud":
            def ask_icloud(again: bool = True):
                c["apple_id"] = ui.ask("Your Apple ID email", c.get("apple_id", ""))
                if again:
                    self.env.pop("ICLOUD_APP_PASSWORD", None)
                self.get_secret("ICLOUD_APP_PASSWORD", "icloud")
            if not c.get("apple_id") or not self.env.get("ICLOUD_APP_PASSWORD"):
                open_url("https://account.apple.com")
                ask_icloud(again=False)
            fix = ask_icloud
        else:
            self.microsoft_signin(c.get("account", "outlook"), c.get("address", "your Microsoft account"))
            def fix():
                self.microsoft_signin(c.get("account", "outlook"), c.get("address", ""), force=True)
            def again():
                self.microsoft_signin(c.get("account", "outlook"), c.get("address", ""))
        options = connectors_from({"calendar": [c]}, None)
        if options:
            self.retry_test(options[0], c["name"], fix, again if p not in ("google", "icloud") else None)

    def microsoft_signin(self, account: str, address: str, force: bool = False) -> None:
        ui = self.ui
        if not self.env.get("OUTLOOK_CLIENT_ID") or force:
            ui.say(HELP["microsoft"].format(address=address or "your Microsoft account"))
            open_url("https://entra.microsoft.com")
            client_id = ui.ask("Paste the Application (client) ID", self.env.get("OUTLOOK_CLIENT_ID", ""))
            if client_id:
                self.save_env(OUTLOOK_CLIENT_ID=client_id)
        Config, build_connector = dashboard_modules()
        conn = build_connector({"type": "outlook", "name": account, "account": account,
                                "client_id_env": "OUTLOOK_CLIENT_ID"}, Config(base_dir=ROOT))
        if conn.token_cache.is_file() and not force:
            return
        ui.say("\nMicrosoft sign-in: open the link below on any device, enter the code, and sign in"
               f" as {address or 'your Microsoft account'}.")
        try:
            conn.login(prompt=ui.say)
            ui.say("  ✔ Signed in to Microsoft.")
        except Exception as exc:
            ui.say(f"  ✘ Microsoft sign-in failed: {exc}")
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                ui.say("    Python can't check Microsoft's certificate. Quit with Ctrl+C, run:\n"
                       "      python3 setup_wizard.py --update\n"
                       "    then choose this step again. Still failing? Double-click\n"
                       "      /Applications/Python 3.13/Install Certificates.command")

    # 5
    def step_telegram(self) -> None:
        ui = self.ui
        header(ui, "Step 5: Telegram (briefings and alerts on your phone)")
        token = self.get_secret("TELEGRAM_BOT_TOKEN", "telegram")
        if not token:
            return
        sys.path.insert(0, str(DASHBOARD))
        from life_dashboard.notify import NotifyError, find_chats, send_telegram
        chat = self.env.get("TELEGRAM_CHAT_ID", "")
        if not chat:
            ui.say("4. Now open your new bot in Telegram (BotFather sent you a t.me/... link) and send it: hi")
            for _ in range(40):  # ~2 minutes
                try:
                    chats = find_chats(token)
                except NotifyError as exc:
                    ui.say(f"  ✘ {exc} (is the token right?)")
                    return
                if chats:
                    chat = chats[0][0]
                    break
                time.sleep(3)
            if not chat:
                ui.say("  ✘ No message received yet. Send the bot 'hi' and run: python3 setup_wizard.py --only telegram")
                return
            self.save_env(TELEGRAM_CHAT_ID=chat)
        try:
            send_telegram(token, chat, "✅ Your assistant is connected. Briefings and alerts will arrive here.")
            ui.say("  ✔ Test message sent. Check Telegram.")
        except NotifyError as exc:
            ui.say(f"  ✘ {exc}")

    # 6
    def step_schedule(self) -> None:
        ui = self.ui
        at = self.answers.get("schedule_time", "07:00")
        header(ui, f"Step 7: Run automatically (dashboard {at}, check-ins 08:00 / 21:00, weekly review Sunday 18:00,"
                   " Telegram bot that answers your questions)")
        jobs = schedule_jobs(VENV_PY, at)
        (HOME / ".exec_assistant").mkdir(exist_ok=True)
        if not IS_MAC:
            ui.say("Not a Mac: add these lines with `crontab -e`:")
            for j in jobs:
                dow = j.get("weekday", "*")
                when = ("@reboot" if j.get("keep_alive") else "*/30 * * * *" if j.get("every")
                        else f"{j['minute']} {j['hour']} * * {dow}")
                ui.say(f"{when} cd {j['workdir']} && {' '.join(j['args'])} >> {LOG_DIR}/{j['name']}.log 2>&1")
            return
        LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
        for j in jobs:
            path = LAUNCH_AGENTS / f"{LABEL}.{j['name']}.plist"
            subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
            path.write_bytes(launchd_plist(j["name"], j["args"], j["workdir"], j.get("hour"), j.get("minute"),
                                           j.get("weekday"), j.get("keep_alive", False), j.get("every")))
            r = subprocess.run(["launchctl", "load", str(path)], capture_output=True, text=True)
            ui.say(f"  ✔ {j['name']}" if r.returncode == 0 else f"  ✘ {j['name']}: {(r.stderr or r.stdout).strip()}")
        h, m = (int(x) for x in at.split(":"))
        wake = f"{(h * 60 + m - 5) // 60 % 24:02d}:{(h * 60 + m - 5) % 60:02d}:00"
        if ui.yes(f"Wake the Mac every day at {wake[:5]} so the morning run never misses? (asks for your Mac password)"):
            subprocess.run(["sudo", "pmset", "repeat", "wakeorpoweron", "MTWRFSU", wake])
        ui.say(f"Logs: {LOG_DIR}")

    def step_google(self) -> None:
        ui = self.ui
        header(ui, "Step 6: Copy your iCloud calendar into Google Calendar (so the Claude app sees it)")
        if not any(c.get("provider") == "icloud" for c in self.answers.get("calendar", [])):
            ui.say("No iCloud calendar set up, so there's nothing to copy. Skipping.")
            return
        address = next((e["address"] for e in self.answers.get("email", []) if e.get("provider") == "gmail"
                        and e.get("group", "").lower() == "personal"), "the Google account the Claude app uses")
        if not (self.env.get("GOOGLE_CLIENT_ID") and self.env.get("GOOGLE_CLIENT_SECRET")) or not ui.yes(
                "Google app details are already saved. Keep them?"):
            ui.say(HELP["google"].format(address=address))
            open_url("https://console.cloud.google.com/projectcreate")
            client_id = ui.ask("Paste the Client ID")
            secret = ui.secret("Paste the Client secret")
            if not (client_id and secret):
                ui.say("  Skipped.")
                return
            self.save_env(GOOGLE_CLIENT_ID=client_id, GOOGLE_CLIENT_SECRET=secret)
        ui.say(f"\nNow sign in as {address} in the browser and click Continue / Allow."
               "\n(If Google says the app isn't verified: Advanced -> Go to Life Assistant. It's your own app.)")
        while True:
            r = subprocess.run([str(VENV_PY), "-m", "life_dashboard", "mirror", "auth"], cwd=DASHBOARD)
            if r.returncode == 0:
                r = subprocess.run([str(VENV_PY), "-m", "life_dashboard", "mirror"], cwd=DASHBOARD,
                                   capture_output=True, text=True)
                ui.say(f"  {'✔' if r.returncode == 0 else '✘'} {(r.stdout or r.stderr).strip()}")
                if r.returncode == 0:
                    ui.say("  It now updates every 30 minutes (installed by the schedule step).")
                    return
            if ui.choose("What now?", ["Try again", "Skip for now"]) == 1:
                return

    # 8
    def step_build(self) -> None:
        header(self.ui, "Step 8: First real dashboard")
        r = subprocess.run([str(VENV_PY), "-m", "life_dashboard", "build", "-q", "--notify"], cwd=DASHBOARD,
                           capture_output=True, text=True)
        self.ui.say(r.stderr.strip())
        html = DASHBOARD / "output" / "dashboard.html"
        if html.exists():
            open_url(html.as_uri())
            if IS_MAC and ICLOUD_DRIVE.is_dir():
                self.ui.say("On your iPhone: Files app -> iCloud Drive -> Life Dashboard -> dashboard.html")

    def run(self, only: str | None = None) -> None:
        self.ui.say("Life Assistant setup. Press Enter to accept a [default]. Ctrl+C stops; re-run any time.")
        for name in STEPS:
            if only and name != only:
                continue
            if not only and name != "python" and not self.ui.yes(f"\nDo step '{name}' now?"):
                continue
            getattr(self, f"step_{name}")()
        if not only:
            check(self.ui)


def check_claude(key: str) -> tuple[bool, str]:
    try:
        import anthropic
    except ImportError:
        return False, "Python packages missing: run python3 setup_wizard.py --only python"
    try:
        anthropic.Anthropic(api_key=key).models.list(limit=1)
        return True, "Claude API key works."
    except anthropic.AuthenticationError:
        return False, "Claude rejected this key (mistyped, or deleted in the console)."
    except anthropic.PermissionDeniedError:
        return False, "Key is valid but not allowed: check billing at https://console.anthropic.com/settings/billing"
    except anthropic.APIConnectionError:
        return False, "Couldn't reach Claude (no internet?). The key is saved; check again later with --check."
    except Exception as exc:
        return False, f"Claude API key check failed: {type(exc).__name__}"


def check(ui: UI | None = None) -> int:
    """Health check: prints one line per item with a fix, returns the number of problems."""
    ui = ui or UI()
    header(ui, "Health check")
    env = read_env()
    os.environ.update({k: v for k, v in env.items() if not os.environ.get(k)})
    problems = 0

    def line(ok: bool, text: str, fix: str = "") -> None:
        nonlocal problems
        problems += not ok
        ui.say(f"  {'✔' if ok else '✘'} {text}" + ("" if ok or not fix else f"\n      fix: {fix}"))

    line(VENV_PY.exists(), "Python environment", "python3 setup_wizard.py --only python")
    if env.get("ANTHROPIC_API_KEY"):
        line(*check_claude(env["ANTHROPIC_API_KEY"]), fix="python3 setup_wizard.py --only claude")
    else:
        line(False, "Claude API key missing (briefings use the offline template)", "python3 setup_wizard.py --only claude")
    vault = Path(env.get("VAULT_PATH", "")).expanduser() if env.get("VAULT_PATH") else None
    line(bool(vault and (vault / "Home.md").exists()), f"Second Brain vault {vault or '(not set)'}",
         "python3 setup_wizard.py --only vault")
    if CONNECTIONS.is_file():
        raw = tomllib.loads(CONNECTIONS.read_text(encoding="utf-8"))
        for c in raw.get("connectors", []):
            ok, detail = test_connector(c, raw.get("timezone", ""))
            line(ok, f"{c.get('name', c['type'])}: {detail}", "python3 setup_wizard.py --only accounts")
    else:
        line(False, "No connections.toml yet", "python3 setup_wizard.py --only accounts")
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        sys.path.insert(0, str(DASHBOARD))
        from life_dashboard.notify import NotifyError, telegram_call
        try:
            telegram_call(env["TELEGRAM_BOT_TOKEN"], "getMe")
            line(True, "Telegram bot")
        except NotifyError as exc:
            line(False, f"Telegram: {exc}", "python3 setup_wizard.py --only telegram")
    else:
        line(False, "Telegram not set up (no phone alerts)", "python3 setup_wizard.py --only telegram")
    if env.get("GOOGLE_CLIENT_ID"):
        signed_in = (HOME / ".config" / "life-dashboard" / "google-calendar.json").is_file()
        line(signed_in, "Google Calendar copy signed in", "python3 setup_wizard.py --only google")
    if IS_MAC:
        loaded = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
        for j in schedule_jobs(VENV_PY):
            line(f"{LABEL}.{j['name']}" in loaded, f"Scheduled: {j['name']}", "python3 setup_wizard.py --only schedule")
    html = DASHBOARD / "output" / "dashboard.html"
    if html.exists():
        age_h = (time.time() - html.stat().st_mtime) / 3600
        line(age_h < 26, f"Dashboard last built {age_h:.0f} hours ago",
             f"check the log in {LOG_DIR}/dashboard.log, or run python3 setup_wizard.py --only build")
    else:
        line(False, "Dashboard never built", "python3 setup_wizard.py --only build")
    ui.say(f"\n{'All good.' if not problems else f'{problems} thing(s) need attention (see fix lines above).'}")
    return problems


def update(ui: UI | None = None) -> int:
    ui = ui or UI()
    header(ui, "Update")
    r = subprocess.run(["git", "pull", "--ff-only"], cwd=ROOT, capture_output=True, text=True)
    ui.say((r.stdout or r.stderr).strip())
    if r.returncode:
        ui.say("✘ Couldn't update automatically (local changes?). Nothing was changed.")
        return 1
    Wizard(ui).step_python()
    return check(ui)


def ensure_venv() -> None:
    """Re-run this script inside .venv so every step uses the same, known Python."""
    if Path(sys.prefix).resolve() == VENV.resolve():
        return
    if VENV_PY.exists() and subprocess.run([str(VENV_PY), "-c", "import sys; sys.exit(sys.version_info < (3, 11))"]).returncode:
        print("Rebuilding .venv with a newer Python (the old one was made with Python < 3.11) ...")
        shutil.rmtree(VENV)
    if not VENV_PY.exists():
        print("Creating a private Python environment in .venv (first run only) ...")
        venv.create(VENV, with_pip=True)
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", *DEPS], check=True)
    os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="health check only")
    parser.add_argument("--update", action="store_true", help="git pull, refresh packages, health check")
    parser.add_argument("--only", choices=STEPS, help="run a single step")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is needed: install it from https://www.python.org/downloads/")
        return 1
    ensure_venv()
    if args.check:
        return 1 if check() else 0
    if args.update:
        return update()
    try:
        Wizard().run(args.only)
    except KeyboardInterrupt:
        print("\nStopped. Everything saved so far is kept; run the wizard again to continue.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
