"""Weekly rollup: deterministic stats in Python, narrative analysis from Claude."""
from __future__ import annotations

from collections import Counter
from datetime import date as Date, timedelta
from pathlib import Path

from . import prompts, vault
from .llm import LLM
from .store import Store

HEAVY_MEETINGS = 4
LOW_ENERGY = 5
SPARK = "▁▂▃▄▅▆▇█"


def week_label(day: Date) -> str:
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def week_range(end: Date, days: int = 7) -> tuple[Date, Date]:
    return end - timedelta(days=days - 1), end


def _rate(rows: list[dict]) -> float | None:
    planned = sum(r["planned"] for r in rows)
    return round(sum(r["completed"] for r in rows) / planned, 3) if planned else None


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _slope(points: list[tuple[int, float]]) -> float:
    if len(points) < 2:
        return 0.0
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    den = sum((x - mx) ** 2 for x, _ in points)
    return round(sum((x - mx) * (y - my) for x, y in points) / den, 2) if den else 0.0


def _day_row(d: dict) -> dict:
    mo, ev, pri = d["morning"], d["evening"], d["priorities"]
    reviewed = ev is not None and bool(pri)
    completed = sum(p["done"] or 0 for p in pri) if reviewed else 0.0
    meetings = next((c["meetings"] for c in (ev, mo) if c and c["meetings"] is not None), None)
    return {
        "date": d["date"], "weekday": Date.fromisoformat(d["date"]).strftime("%a"),
        "morning": mo is not None, "evening": ev is not None, "reviewed": reviewed,
        "planned": len(pri) if reviewed else 0, "completed": completed,
        "rate": round(completed / len(pri), 3) if reviewed else None,
        "energy": _mean([mo and mo["energy"], ev and ev["energy"]]),
        "mood": ev["mood"] if ev else None, "meetings": meetings, "tags": d["tags"],
    }


def _compare(rows, pred, label_a: str, label_b: str, threshold: float) -> str | None:
    a = [r for r in rows if pred(r)]
    b = [r for r in rows if not pred(r)]
    ra, rb = _rate(a), _rate(b)
    if ra is None or rb is None or abs(ra - rb) < threshold:
        return None
    return f"Completion was {ra:.0%} on {label_a} vs {rb:.0%} on {label_b}."


def compute_stats(days: list[dict], start: Date, end: Date) -> dict:
    rows = [_day_row(d) for d in days]
    reviewed = [r for r in rows if r["reviewed"]]
    tag_counts = Counter(t for r in rows for t in r["tags"])
    energy_pts = [((Date.fromisoformat(r["date"]) - start).days, r["energy"])
                  for r in rows if r["energy"] is not None]
    slope = _slope(energy_pts)

    patterns = []
    with_meetings = [r for r in reviewed if r["meetings"] is not None]
    if p := _compare(with_meetings, lambda r: r["meetings"] >= HEAVY_MEETINGS,
                     f"meeting-heavy days ({HEAVY_MEETINGS}+ meetings)", "lighter days", 0.15):
        patterns.append(p)
    with_energy = [r for r in reviewed if r["energy"] is not None]
    if p := _compare(with_energy, lambda r: r["energy"] <= LOW_ENERGY,
                     f"low-energy days (<= {LOW_ENERGY}/10)", "higher-energy days", 0.15):
        patterns.append(p)
    for tag, n in tag_counts.most_common():
        if n >= 2 and (p := _compare(reviewed, lambda r, t=tag: t in r["tags"],
                                     f"days tagged #{tag}", "other days", 0.2)):
            patterns.append(p)

    # Priorities that showed up on 2+ days and were still not done the last time.
    seen: dict[str, list] = {}
    for d in days:
        for p in d["priorities"]:
            seen.setdefault(p["text"].strip().lower(), []).append(p)
    carried = [ps[-1]["text"] for ps in seen.values() if len(ps) >= 2 and (ps[-1]["done"] or 0) < 1]

    ranked = sorted((r for r in reviewed if r["planned"]), key=lambda r: (r["rate"], r["completed"]))
    collect = lambda kind, key: [  # noqa: E731
        {"date": d["date"], "text": t} for d in days if d[kind]
        for t in (d[kind]["data"].get(key) if isinstance(d[kind]["data"].get(key), list)
                  else [d[kind]["data"].get(key)]) if t]
    n_days = (end - start).days + 1
    return {
        "week": week_label(end), "start": start.isoformat(), "end": end.isoformat(),
        "days_logged": len([r for r in rows if r["morning"] or r["evening"]]),
        "missed_mornings": n_days - sum(r["morning"] for r in rows),
        "missed_evenings": n_days - sum(r["evening"] for r in rows),
        "planned_reviewed": sum(r["planned"] for r in reviewed),
        "completed": sum(r["completed"] for r in reviewed),
        "completion_rate": _rate(reviewed),
        "avg_energy": _mean(r["energy"] for r in rows),
        "avg_mood": _mean(r["mood"] for r in rows),
        "energy_slope": slope,
        "energy_trend": "rising" if slope >= 0.3 else "falling" if slope <= -0.3 else "flat",
        "root_causes": tag_counts.most_common(),
        "recurring_root_causes": [t for t, n in tag_counts.most_common() if n >= 2],
        "patterns": patterns,
        "best_day": ranked[-1] if ranked else None,
        "worst_day": ranked[0] if ranked else None,
        "carried_over": carried,
        "wins": collect("evening", "wins"),
        "blockers": collect("morning", "blockers"),
        "lessons": collect("evening", "lessons"),
        "daily": rows,
    }


def sparkline(values) -> str:
    return "".join(SPARK[min(7, max(0, round((v - 1) / 9 * 7)))] if v is not None else "·"
                   for v in values)


def render_stats_md(s: dict) -> str:
    pct = lambda v: f"{v:.0%}" if v is not None else "–"  # noqa: E731
    lines = ["| Date | Day | Done | Rate | Energy | Mood | Mtgs | Root causes |",
             "|---|---|---|---|---|---|---|---|"]
    for r in s["daily"]:
        done = f"{r['completed']:g}/{r['planned']}" if r["reviewed"] else "–"
        lines.append(f"| {r['date']} | {r['weekday']} | {done} | {pct(r['rate'])} | "
                     f"{r['energy'] if r['energy'] is not None else '–'} | {r['mood'] or '–'} | "
                     f"{r['meetings'] if r['meetings'] is not None else '–'} | "
                     f"{', '.join(r['tags']) or '–'} |")
    out = ["## By the numbers",
           f"- **Completion:** {s['completed']:g}/{s['planned_reviewed']} priorities ({pct(s['completion_rate'])})",
           f"- **Energy:** avg {s['avg_energy'] or '–'}/10, trend {s['energy_trend']} "
           f"({s['energy_slope']:+}/day) `{sparkline(r['energy'] for r in s['daily'])}`",
           f"- **Mood:** avg {s['avg_mood'] or '–'}/10",
           f"- **Check-ins:** {s['days_logged']}/7 days logged; missed {s['missed_mornings']} "
           f"mornings, {s['missed_evenings']} evenings"]
    if s["root_causes"]:
        out.append("- **Root causes:** " + ", ".join(f"#{t} ×{n}" for t, n in s["root_causes"]))
    if s["best_day"]:
        out.append(f"- **Best day:** {s['best_day']['weekday']} {s['best_day']['date']} "
                   f"({pct(s['best_day']['rate'])}) · **Toughest:** {s['worst_day']['weekday']} "
                   f"{s['worst_day']['date']} ({pct(s['worst_day']['rate'])})")
    out += ["", *lines]
    if s["patterns"]:
        out += ["", "### Patterns", *[f"- {p}" for p in s["patterns"]]]
    if s["carried_over"]:
        out += ["", "### Carried over (planned 2+ days, still open)", *[f"- {c}" for c in s["carried_over"]]]
    if s["wins"]:
        out += ["", "### Wins", *[f"- {w['text']} *({w['date']})*" for w in s["wins"]]]
    return "\n".join(out)


def _compact(days: list[dict]) -> list[dict]:
    out = []
    for d in days:
        e = (d["evening"] or {}).get("data", {})
        m = (d["morning"] or {}).get("data", {})
        out.append({"date": d["date"], "priorities": [[p["text"], p["done"]] for p in d["priorities"]],
                    "blockers": m.get("blockers"), "wins": e.get("wins"),
                    "didnt_go_well": e.get("didnt_go_well"), "tags": d["tags"],
                    "lessons": e.get("lessons")})
    return out


def run_weekly(store: Store, llm: LLM, end: Date, out_dir: Path | None = None,
               out_path: Path | None = None, vault_path: Path | None = None) -> dict:
    start, end = week_range(end)
    days = store.days(start.isoformat(), end.isoformat())
    stats = compute_stats(days, start, end)
    analysis = llm.generate(prompts.SYSTEM, prompts.weekly_prompt(stats, _compact(days)),
                            lambda: prompts.dry_weekly(stats))
    body = f"{render_stats_md(stats)}\n\n## Analysis\n\n{analysis.strip()}\n"
    markdown = f"# Weekly Review {stats['week']} ({stats['start']} → {stats['end']})\n\n{body}"
    store.save_weekly(stats["week"], stats["start"], stats["end"], stats, markdown)
    path = out_path or ((out_dir / f"weekly-{stats['week']}.md") if out_dir else None)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown)
    note = (vault.write_weekly(vault_path, stats["week"],
                               f"## Weekly review ({stats['start']} → {stats['end']})\n\n{body}")
            if vault_path else None)
    return {"stats": stats, "markdown": markdown, "path": path, "note": note}
