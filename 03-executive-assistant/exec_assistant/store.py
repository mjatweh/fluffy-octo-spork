"""SQLite persistence for check-ins, priorities, root-cause tags and weekly reports."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS checkins (
    date TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('morning', 'evening')),
    energy INTEGER, mood INTEGER, meetings INTEGER,
    data TEXT NOT NULL, response TEXT, created_at TEXT NOT NULL,
    PRIMARY KEY (date, kind)
);
CREATE TABLE IF NOT EXISTS priorities (
    date TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL,
    done REAL,  -- NULL = not reviewed yet, 0 = no, 0.5 = partial, 1 = done
    PRIMARY KEY (date, position)
);
CREATE TABLE IF NOT EXISTS tags (
    date TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY (date, tag)
);
CREATE TABLE IF NOT EXISTS weekly_reports (
    week TEXT PRIMARY KEY, start TEXT NOT NULL, end TEXT NOT NULL,
    stats TEXT NOT NULL, markdown TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- check-ins -------------------------------------------------------
    def save_checkin(self, date: str, kind: str, data: dict, response: str = "",
                     energy: int | None = None, mood: int | None = None,
                     meetings: int | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO checkins VALUES (?,?,?,?,?,?,?,?)",
                (date, kind, energy, mood, meetings, json.dumps(data), response, _now()),
            )

    def get_checkin(self, date: str, kind: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM checkins WHERE date=? AND kind=?", (date, kind)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["data"] = json.loads(out["data"])
        return out

    def last_checkin_before(self, date: str, kind: str) -> dict | None:
        row = self.conn.execute(
            "SELECT date FROM checkins WHERE kind=? AND date<? ORDER BY date DESC LIMIT 1",
            (kind, date)).fetchone()
        return self.get_checkin(row["date"], kind) if row else None

    def delete_day(self, date: str) -> None:
        with self.conn:
            for table in ("checkins", "priorities", "tags"):
                self.conn.execute(f"DELETE FROM {table} WHERE date=?", (date,))

    # --- priorities ------------------------------------------------------
    def set_priorities(self, date: str, texts: list[str]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM priorities WHERE date=?", (date,))
            self.conn.executemany(
                "INSERT INTO priorities (date, position, text, done) VALUES (?,?,?,NULL)",
                [(date, i, t) for i, t in enumerate(texts)])

    def mark_priority(self, date: str, position: int, done: float | None) -> None:
        with self.conn:
            self.conn.execute("UPDATE priorities SET done=? WHERE date=? AND position=?",
                              (done, date, position))

    def get_priorities(self, date: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT position, text, done FROM priorities WHERE date=? ORDER BY position",
            (date,)).fetchall()
        return [dict(r) for r in rows]

    # --- tags ------------------------------------------------------------
    def set_tags(self, date: str, tags: list[str]) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tags WHERE date=?", (date,))
            self.conn.executemany("INSERT OR IGNORE INTO tags VALUES (?,?)",
                                  [(date, t) for t in tags])

    def get_tags(self, date: str) -> list[str]:
        return [r["tag"] for r in self.conn.execute(
            "SELECT tag FROM tags WHERE date=? ORDER BY tag", (date,))]

    # --- aggregate views -------------------------------------------------
    def dates(self, start: str | None = None, end: str | None = None) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT date FROM (SELECT date FROM checkins UNION SELECT date FROM priorities)"
            " WHERE date >= ? AND date <= ? ORDER BY date",
            (start or "0000-00-00", end or "9999-99-99")).fetchall()
        return [r["date"] for r in rows]

    def day(self, date: str) -> dict:
        return {
            "date": date,
            "morning": self.get_checkin(date, "morning"),
            "evening": self.get_checkin(date, "evening"),
            "priorities": self.get_priorities(date),
            "tags": self.get_tags(date),
        }

    def days(self, start: str, end: str) -> list[dict]:
        return [self.day(d) for d in self.dates(start, end)]

    # --- weekly reports --------------------------------------------------
    def save_weekly(self, week: str, start: str, end: str, stats: dict, markdown: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO weekly_reports VALUES (?,?,?,?,?,?)",
                              (week, start, end, json.dumps(stats), markdown, _now()))

    def get_weekly(self, week: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM weekly_reports WHERE week=?", (week,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["stats"] = json.loads(out["stats"])
        return out
