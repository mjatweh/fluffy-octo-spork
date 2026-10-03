"""Print snippets that run ``build`` every morning: cron, launchd, systemd, GitHub Actions."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import PROJECT_DIR, Config

FORMATS = ("cron", "launchd", "systemd", "github")


def _hm(at: str) -> tuple[int, int]:
    h, m = at.split(":")
    hour, minute = int(h), int(m)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"Invalid time: {at}")
    return hour, minute


def to_utc(at: str, config: Config) -> tuple[int, int]:
    hour, minute = _hm(at)
    local = datetime.now(config.tz).replace(hour=hour, minute=minute, second=0, microsecond=0)
    utc = local.astimezone(timezone.utc)
    return utc.hour, utc.minute


def snippet(fmt: str, at: str, config: Config, python: str | None = None, project: Path | None = None) -> str:
    hour, minute = _hm(at)
    py = python or sys.executable
    proj = Path(project or PROJECT_DIR)
    args = "build" + (f" --config {config.source_file}" if config.source_file else "")
    log = proj / "output" / "build.log"

    if fmt == "cron":
        tz_line = f"CRON_TZ={config.timezone}\n" if config.timezone else ""
        return (
            f"# Life Dashboard — every day at {at}. Install with: crontab -e\n"
            f"# (.env in the project folder is loaded automatically, so ANTHROPIC_API_KEY can live there)\n"
            f"{tz_line}{minute} {hour} * * * cd {proj} && mkdir -p output && {py} -m life_dashboard {args} --quiet >> {log} 2>&1\n"
        )
    if fmt == "launchd":
        prog = "".join(f"\n        <string>{a}</string>" for a in [py, "-m", "life_dashboard", *args.split()])
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Save as ~/Library/LaunchAgents/com.life-dashboard.daily.plist, then:
     launchctl load ~/Library/LaunchAgents/com.life-dashboard.daily.plist -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.life-dashboard.daily</string>
    <key>WorkingDirectory</key><string>{proj}</string>
    <key>ProgramArguments</key>
    <array>{prog}
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
    <key>StandardOutPath</key><string>{log}</string>
    <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""
    if fmt == "systemd":
        return f"""# ~/.config/systemd/user/life-dashboard.service
[Unit]
Description=Life Dashboard morning build

[Service]
Type=oneshot
WorkingDirectory={proj}
ExecStart={py} -m life_dashboard {args}

# ~/.config/systemd/user/life-dashboard.timer
[Unit]
Description=Run Life Dashboard every morning

[Timer]
OnCalendar=*-*-* {hour:02d}:{minute:02d}:00
Persistent=true

[Install]
WantedBy=timers.target

# Enable with: systemctl --user daemon-reload && systemctl --user enable --now life-dashboard.timer
"""
    if fmt == "github":
        uh, um = to_utc(at, config)
        return f"""# .github/workflows/life-dashboard.yml  (at the repository root)
# GitHub cron is UTC: {at} in {config.timezone or 'local time'} is {uh:02d}:{um:02d} UTC today
# (adjust after daylight-saving changes). Add ANTHROPIC_API_KEY under Settings → Secrets → Actions.
name: Life Dashboard
on:
  schedule:
    - cron: "{um} {uh} * * *"
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: 01-life-dashboard
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python -m life_dashboard build
        env:
          ANTHROPIC_API_KEY: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
          # IMAP_PASSWORD: ${{{{ secrets.IMAP_PASSWORD }}}}
      - uses: actions/upload-artifact@v4
        with:
          name: dashboard
          path: 01-life-dashboard/output/
"""
    raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(FORMATS)}")
