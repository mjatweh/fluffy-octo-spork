import datetime as dt

from second_brain.reminders import format_table, upcoming

TODAY = dt.date(2026, 10, 3)


def test_upcoming_within_window(ingested):
    rows = upcoming(ingested, days=60, today=TODAY)
    assert [(r["date"], r["label"], r["name"]) for r in rows] == [
        ("2026-10-17", "due", "Invoice 2026-0917"),
        ("2026-11-15", "expiry", "Auto Insurance Policy Declarations"),
    ]
    assert rows[0]["days_left"] == 14


def test_longer_window_includes_lease_and_contract(ingested):
    labels = {(r["name"], r["label"]) for r in upcoming(ingested, days=365, today=TODAY)}
    assert ("Residential Lease Agreement", "notice deadline") in labels
    assert ("Residential Lease Agreement", "renewal") in labels
    assert ("Consulting Services Agreement", "expiry") in labels
    assert not any(label in ("start", "signed") for _, label in labels)  # history isn't a reminder


def test_overdue(ingested):
    later = dt.date(2026, 10, 20)
    assert all(r["days_left"] >= 0 for r in upcoming(ingested, 30, today=later))
    overdue = upcoming(ingested, 30, today=later, include_overdue=True)
    assert overdue[0]["name"] == "Invoice 2026-0917" and overdue[0]["days_left"] == -3


def test_format_table():
    assert format_table([]) == "No upcoming dates."
    line = format_table([{"date": "2026-10-17", "days_left": 14, "label": "due", "name": "Invoice"}])
    assert "in 14d" in line and "[[Invoice]]" in line
