"""Deal-flow tools: intake, return math, criteria checks, pipeline tracker and memos.

The deals folder ($DEALS_DIR, default <workspace>/deals/) holds:
  - criteria.toml   investment criteria per asset class (start from examples/deals/criteria.example.toml)
  - inbox/          deals to screen: pasted listings (e.g. from a deal app), forwarded emails (.eml),
                    teasers / offering memos (.txt, .md, .pdf with pypdf installed)
  - pipeline.csv    one row per deal, maintained by the agent
  - memos/          screening memos and investor one-pagers
Nothing here contacts brokers, sellers or investors: outreach stays with the owner.
"""
from __future__ import annotations

import csv
import datetime as dt
import email
import email.policy
import io
import os
import re
import tomllib
from pathlib import Path

from .agent import ToolContext
from .registry import ToolRegistry

STAGES = ["new", "screening", "diligence", "loi", "under_contract", "closed", "passed"]
PIPELINE_FIELDS = ["id", "name", "asset_class", "source", "stage", "ask", "key_metric", "recommendation",
                   "next_step", "owner", "updated", "memo"]
DOC_TYPES = {".txt", ".md", ".eml", ".pdf", ".csv"}
MAX_DOC = 25_000


def deals_dir(ctx: ToolContext) -> Path:
    return Path(os.environ.get("DEALS_DIR") or Path(ctx.workspace) / "deals").expanduser()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "deal"


# --- documents --------------------------------------------------------------------------------

def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".eml":
        msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
        body = msg.get_body(preferencelist=("plain", "html"))
        text = body.get_content() if body else ""
        if body is not None and body.get_content_type() == "text/html":
            text = re.sub(r"<[^>]+>", " ", text)
        head = f"From: {msg['from']}\nSubject: {msg['subject']}\nDate: {msg['date']}\n\n"
        return head + re.sub(r"[ \t]+", " ", text)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return "[PDF text extraction needs `pip install pypdf`; ask the owner for the key numbers instead]"
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="replace")


# --- return math --------------------------------------------------------------------------------

def npv(rate: float, cash_flows: list[float]) -> float:
    return sum(cf / (1 + rate) ** i for i, cf in enumerate(cash_flows))


def irr(cash_flows: list[float]) -> float | None:
    """Annual IRR by bisection (cash_flows[0] is the investment, negative). None if it doesn't exist."""
    if not cash_flows or not any(c < 0 for c in cash_flows) or not any(c > 0 for c in cash_flows):
        return None
    lo, hi = -0.99, 10.0
    if npv(lo, cash_flows) * npv(hi, cash_flows) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo, cash_flows) * npv(mid, cash_flows) <= 0:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2 * 100, 2)


def returns(cash_flows: list[float]) -> dict:
    invested = -sum(c for c in cash_flows if c < 0)
    returned = sum(c for c in cash_flows if c > 0)
    return {"irr_pct": irr(cash_flows), "moic": round(returned / invested, 2) if invested else None,
            "profit": round(returned - invested, 2), "years": len(cash_flows) - 1}


def real_estate(price: float, noi: float, loan_pct: float = 0.0, rate_pct: float = 0.0,
                amort_years: int = 30, closing_cost_pct: float = 2.0) -> dict:
    loan = price * loan_pct / 100
    equity = price - loan + price * closing_cost_pct / 100
    if loan and rate_pct:
        r, n = rate_pct / 100 / 12, amort_years * 12
        debt_service = loan * r / (1 - (1 + r) ** -n) * 12
    else:
        debt_service = 0.0
    cash_flow = noi - debt_service
    return {
        "cap_rate_pct": round(noi / price * 100, 2) if price else None,
        "loan": round(loan, 2), "equity_required": round(equity, 2),
        "annual_debt_service": round(debt_service, 2),
        "dscr": round(noi / debt_service, 2) if debt_service else None,
        "cash_flow_after_debt": round(cash_flow, 2),
        "cash_on_cash_pct": round(cash_flow / equity * 100, 2) if equity else None,
    }


# --- criteria ---------------------------------------------------------------------------------

def load_criteria(folder: Path) -> dict:
    path = folder / "criteria.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def check_against(criteria: dict, asset_class: str, metrics: dict) -> dict:
    """Compare metrics to ``criteria[asset_class]``: keys ``min_<metric>`` / ``max_<metric>``."""
    rules = criteria.get(asset_class, {})
    if not rules:
        return {"asset_class": asset_class, "checked": [], "note": f"no criteria for '{asset_class}' in criteria.toml"}
    checked, fails, missing = [], [], []
    for key, limit in rules.items():
        if not isinstance(limit, (int, float)) or not key.startswith(("min_", "max_")):
            continue
        metric = key[4:]
        value = metrics.get(metric)
        if value is None:
            missing.append(metric)
            continue
        ok = value >= limit if key.startswith("min_") else value <= limit
        checked.append({"metric": metric, "value": value, "rule": f"{key[:3]} {limit}", "pass": ok})
        if not ok:
            fails.append(metric)
    return {"asset_class": asset_class, "checked": checked, "fails": fails, "missing": missing,
            "meets_criteria": not fails and not missing,
            "notes": {k: v for k, v in rules.items() if not isinstance(v, (int, float))}}


# --- pipeline ---------------------------------------------------------------------------------

def read_pipeline(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def upsert(rows: list[dict], deal: dict) -> list[dict]:
    deal = {k: str(v) for k, v in deal.items() if k in PIPELINE_FIELDS and v not in (None, "")}
    deal["id"] = deal.get("id") or slug(deal.get("name", ""))
    if deal.get("stage") and deal["stage"] not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    deal["updated"] = dt.date.today().isoformat()
    for row in rows:
        if row["id"] == deal["id"]:
            row.update(deal)
            return rows
    return rows + [{**{f: "" for f in PIPELINE_FIELDS}, "stage": "new", **deal}]


def write_pipeline(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=PIPELINE_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


# --- tool registration ------------------------------------------------------------------------

def register_deal_tools(reg: ToolRegistry) -> None:
    @reg.tool()
    def deal_criteria(ctx: ToolContext) -> dict:
        """The family office's investment criteria per asset class (criteria.toml in the deals folder)."""
        criteria = load_criteria(deals_dir(ctx))
        return criteria or {"note": "No criteria.toml yet; copy examples/deals/criteria.example.toml into the deals folder."}

    @reg.tool()
    def deal_inbox(ctx: ToolContext) -> dict:
        """Deal documents waiting in the inbox, marking which ones are already in the pipeline."""
        folder = deals_dir(ctx)
        tracked = {r.get("source", "") for r in read_pipeline(folder / "pipeline.csv")}
        files = sorted(p for p in (folder / "inbox").glob("*") if p.suffix.lower() in DOC_TYPES)
        return {"files": [{"name": p.name, "in_pipeline": p.name in tracked, "kb": round(p.stat().st_size / 1024, 1)}
                          for p in files],
                "folder": str(folder / "inbox")}

    @reg.tool(params={"name": "File name inside the deals inbox"})
    def read_deal_document(ctx: ToolContext, name: str) -> str:
        """Text of a deal document from the inbox (teaser, offering memo, forwarded email, pasted listing)."""
        inbox = (deals_dir(ctx) / "inbox").resolve()
        path = (inbox / name).resolve()
        if inbox not in path.parents or not path.is_file():
            raise ValueError(f"not a file in the deals inbox: {name}")
        text = read_document(path)
        return text if len(text) <= MAX_DOC else text[:MAX_DOC] + "\n...[truncated]"

    @reg.tool(params={"price": "Purchase price", "noi": "Net operating income per year",
                      "loan_pct": "Loan as % of price (0 for all cash)", "rate_pct": "Interest rate %",
                      "amort_years": "Amortization in years", "closing_cost_pct": "Closing costs as % of price"})
    def real_estate_metrics(price: float, noi: float, loan_pct: float = 0.0, rate_pct: float = 0.0,
                            amort_years: int = 30, closing_cost_pct: float = 2.0) -> dict:
        """Cap rate, debt service, DSCR, equity required and cash-on-cash return for a property."""
        return real_estate(price, noi, loan_pct, rate_pct, amort_years, closing_cost_pct)

    @reg.tool(params={"cash_flows": "Yearly cash flows; first is the investment (negative), e.g. [-1000000, 80000, 80000, 1300000]"})
    def investment_returns(cash_flows: list[float]) -> dict:
        """IRR, multiple on invested capital (MOIC) and profit from yearly cash flows."""
        return returns([float(c) for c in cash_flows])

    @reg.tool(params={"asset_class": "Section of criteria.toml, e.g. real_estate, operating_business, venture, funds",
                      "metrics": "Deal metrics, e.g. {\"cap_rate_pct\": 7.1, \"dscr\": 1.4, \"check_size\": 2000000}"})
    def check_deal_criteria(ctx: ToolContext, asset_class: str, metrics: dict) -> dict:
        """Check a deal's metrics against the family office's criteria; lists passes, fails and missing data."""
        return check_against(load_criteria(deals_dir(ctx)), asset_class, metrics)

    @reg.tool(params={"stage": "Optional stage filter"})
    def deal_pipeline(ctx: ToolContext, stage: str = "") -> dict:
        """The deal pipeline tracker, with counts per stage."""
        rows = read_pipeline(deals_dir(ctx) / "pipeline.csv")
        counts = {s: sum(r.get("stage") == s for r in rows) for s in STAGES}
        return {"deals": [r for r in rows if not stage or r.get("stage") == stage], "counts": counts}

    @reg.tool(params={"name": "Deal name", "id": "Existing deal id (to update)", "asset_class": "Asset class",
                      "source": "Where it came from (inbox file name, broker, app, referral)",
                      "stage": f"One of: {', '.join(STAGES)}", "ask": "Asking price / raise",
                      "key_metric": "Headline metric, e.g. '7.1% cap, 1.4x DSCR'", "recommendation": "pursue / pass / more info",
                      "next_step": "Next action", "owner": "Who owns the next step", "memo": "Memo file name"})
    def update_pipeline(ctx: ToolContext, name: str = "", id: str = "", asset_class: str = "", source: str = "",
                        stage: str = "", ask: str = "", key_metric: str = "", recommendation: str = "",
                        next_step: str = "", owner: str = "", memo: str = "") -> str:
        """Add a deal to the pipeline tracker or update an existing one (matched by id, else by name)."""
        if not (name or id):
            raise ValueError("give a deal name or id")
        path = deals_dir(ctx) / "pipeline.csv"
        rows = upsert(read_pipeline(path), dict(name=name, id=id, asset_class=asset_class, source=source, stage=stage,
                                                ask=ask, key_metric=key_metric, recommendation=recommendation,
                                                next_step=next_step, owner=owner, memo=memo))
        write_pipeline(path, rows)
        return f"pipeline updated ({len(rows)} deals)"

    @reg.tool(params={"title": "Memo title, e.g. deal name", "markdown": "Full memo in markdown",
                      "kind": "memo (default) or one-pager"})
    def save_deal_memo(ctx: ToolContext, title: str, markdown: str, kind: str = "memo") -> str:
        """Save a screening memo or investor one-pager to the deals folder's memos/."""
        folder = deals_dir(ctx) / "memos"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{dt.date.today().isoformat()}-{slug(title)}{'-one-pager' if kind == 'one-pager' else ''}.md"
        (folder / name).write_text(markdown, encoding="utf-8")
        return f"saved memos/{name}"
