"""Trading analyst tools: holdings, price technicals, "smart money" signals and risk checks.

Analysis only. There is deliberately no tool that places, changes or cancels an order:
the owner reviews the ideas and trades in their own apps.

Data lives in the trading folder ($TRADING_DIR, default <workspace>/trading/):
  - Revolut trading statement exports (*.csv with Date,Ticker,Type,Quantity,... columns)
  - holdings.csv for anything else (e.g. Autopilot): account,ticker,shares,cost_basis
  - profile.toml: risk tolerance, horizon and position limits (see profile.example.toml)
Prices come from Stooq's free daily CSV (no key). Politician, insider and 13F data come from
the Quiver Quant API when QUIVER_API_TOKEN is set.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .agent import ToolContext
from .registry import ToolRegistry

PRICE_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
QUIVER_URL = "https://api.quiverquant.com/beta"
QUIVER_ENDPOINTS = {  # override under [quiver] in profile.toml if Quiver changes paths
    "congress": "/historical/congresstrading/{ticker}",
    "insiders": "/live/insiders?ticker={ticker}",
    "institutions": "/live/sec13f?ticker={ticker}",
}
DEFAULT_PROFILE = {
    "risk_tolerance": "moderate",
    "horizon_years": 3,
    "max_position_pct": 10.0,
    "max_speculative_pct": 20.0,
    "stop_loss_pct": 15.0,
    "notes": "",
}

Fetch = Callable[[str, dict], str]


def http_get(url: str, headers: dict) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ai-workforce/1.0", **headers})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def trading_dir(ctx: ToolContext) -> Path:
    return Path(os.environ.get("TRADING_DIR") or Path(ctx.workspace) / "trading").expanduser()


# --- holdings -----------------------------------------------------------------------------------

@dataclass
class Position:
    account: str
    ticker: str
    shares: float
    cost_basis: float  # total, in the account currency

    @property
    def avg_cost(self) -> float:
        return self.cost_basis / self.shares if self.shares else 0.0


def _money(value: str) -> float:
    """'USD 1,234.50' / '$1,234.50' / '-12.3' -> float (0.0 when empty)."""
    cleaned = re.sub(r"[^0-9.\-]", "", value or "")
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else 0.0
    except ValueError:
        return 0.0


def parse_revolut(text: str, account: str = "Revolut") -> list[Position]:
    """Rebuild open positions from a Revolut trading statement (average-cost method)."""
    shares: dict[str, float] = defaultdict(float)
    cost: dict[str, float] = defaultdict(float)
    rows = sorted(csv.DictReader(io.StringIO(text)), key=lambda r: r.get("Date", ""))
    for r in rows:
        ticker, kind = (r.get("Ticker") or "").strip().upper(), (r.get("Type") or "").upper()
        qty = _money(r.get("Quantity", ""))
        if not ticker or not qty:
            continue
        if kind.startswith("BUY"):
            shares[ticker] += qty
            cost[ticker] += abs(_money(r.get("Total Amount", ""))) or qty * _money(r.get("Price per share", ""))
        elif kind.startswith("SELL") and shares[ticker]:
            sold = min(qty, shares[ticker])
            cost[ticker] -= cost[ticker] * sold / shares[ticker]
            shares[ticker] -= sold
        elif "SPLIT" in kind:  # Revolut books the change in share count; total cost is unchanged
            shares[ticker] += qty
    return [Position(account, t, round(s, 6), round(cost[t], 2)) for t, s in sorted(shares.items()) if s > 1e-9]


def parse_holdings(text: str) -> list[Position]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        ticker = (r.get("ticker") or "").strip().upper()
        if ticker and _money(r.get("shares", "")):
            out.append(Position((r.get("account") or "Manual").strip(), ticker, _money(r["shares"]),
                                _money(r.get("cost_basis", ""))))
    return out


def load_positions(folder: Path) -> list[Position]:
    positions: list[Position] = []
    for path in sorted(folder.glob("*.csv")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        header = text.split("\n", 1)[0].lower()
        if "ticker" in header and "type" in header and "quantity" in header:
            positions += parse_revolut(text)
        elif "ticker" in header and "shares" in header:
            positions += parse_holdings(text)
    return positions


def load_watchlist(folder: Path) -> list[str]:
    path = folder / "watchlist.txt"
    if not path.is_file():
        return []
    words = re.split(r"[\s,]+", re.sub(r"#.*", "", path.read_text(encoding="utf-8")))
    return list(dict.fromkeys(w.upper() for w in words if w))


def load_profile(folder: Path) -> dict:
    path = folder / "profile.toml"
    profile = dict(DEFAULT_PROFILE)
    if path.is_file():
        with path.open("rb") as fh:
            profile.update(tomllib.load(fh))
    return profile


# --- prices & technicals ------------------------------------------------------------------------

def parse_prices(text: str) -> list[tuple[str, float]]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        close = _money(r.get("Close", ""))
        if r.get("Date") and close:
            rows.append((r["Date"], close))
    return rows


def sma(values: list[float], n: int) -> float | None:
    return round(sum(values[-n:]) / n, 4) if len(values) >= n else None


def rsi(values: list[float], n: int = 14) -> float | None:
    if len(values) <= n:
        return None
    gains = losses = 0.0
    for a, b in zip(values[-n - 1:-1], values[-n:]):
        change = b - a
        gains += max(change, 0)
        losses += max(-change, 0)
    if losses == 0:
        return 100.0
    return round(100 - 100 / (1 + gains / losses), 1)


def technicals(closes: list[float]) -> dict:
    if not closes:
        return {"error": "no price data"}
    last = closes[-1]

    def ret(days: int) -> float | None:
        return round((last / closes[-days - 1] - 1) * 100, 2) if len(closes) > days else None

    s50, s200 = sma(closes, 50), sma(closes, 200)
    year = closes[-252:]
    trend = "unknown"
    if s50 and s200:
        trend = "uptrend" if last > s50 > s200 else "downtrend" if last < s50 < s200 else "mixed"
    return {
        "last": last, "change_1d_pct": ret(1), "change_5d_pct": ret(5), "change_1m_pct": ret(21),
        "change_3m_pct": ret(63), "sma50": s50, "sma200": s200, "rsi14": rsi(closes), "trend": trend,
        "from_52w_high_pct": round((last / max(year) - 1) * 100, 2),
        "from_52w_low_pct": round((last / min(year) - 1) * 100, 2),
    }


def fetch_closes(ticker: str, fetch: Fetch = http_get) -> list[float]:
    symbol = ticker.lower() if "." in ticker else f"{ticker.lower()}.us"
    url = os.environ.get("PRICE_CSV_URL", PRICE_URL).format(symbol=urllib.parse.quote(symbol))
    return [c for _, c in parse_prices(fetch(url, {}))]


# --- smart money (Quiver Quant) -------------------------------------------------------------------

def smart_money(ticker: str, token: str, endpoints: dict | None = None, fetch: Fetch = http_get,
                limit: int = 10) -> dict:
    out: dict = {}
    for key, path in {**QUIVER_ENDPOINTS, **(endpoints or {})}.items():
        url = QUIVER_URL + path.format(ticker=urllib.parse.quote(ticker.upper()))
        try:
            rows = json.loads(fetch(url, {"Authorization": f"Token {token}", "Accept": "application/json"}))
            out[key] = rows[:limit] if isinstance(rows, list) else rows
        except (OSError, ValueError) as exc:
            out[key] = {"error": f"HTTP {exc.code}" if hasattr(exc, "code") else type(exc).__name__}
    return out


# --- risk ---------------------------------------------------------------------------------------

def check_idea(profile: dict, action: str, pct_of_portfolio: float, current_pct: float = 0.0,
               speculative: bool = False, speculative_pct_now: float = 0.0) -> dict:
    warnings = []
    after = current_pct + pct_of_portfolio if action.lower() == "buy" else max(current_pct - pct_of_portfolio, 0)
    if action.lower() == "buy" and after > profile["max_position_pct"]:
        warnings.append(f"position would be {after:.1f}% of the portfolio; your limit is {profile['max_position_pct']}%")
    if speculative and action.lower() == "buy" and speculative_pct_now + pct_of_portfolio > profile["max_speculative_pct"]:
        warnings.append(f"speculative bucket would reach {speculative_pct_now + pct_of_portfolio:.1f}%; "
                        f"limit {profile['max_speculative_pct']}%")
    return {"within_limits": not warnings, "position_after_pct": round(after, 2), "warnings": warnings,
            "suggested_stop_loss_pct": profile["stop_loss_pct"]}


# --- tool registration ----------------------------------------------------------------------------

def register_trading_tools(reg: ToolRegistry, fetch: Fetch = http_get) -> None:
    @reg.tool()
    def risk_profile(ctx: ToolContext) -> dict:
        """The owner's risk tolerance, time horizon and position limits (from the trading folder's profile.toml)."""
        return load_profile(trading_dir(ctx))

    @reg.tool(params={"with_prices": "Fetch latest prices to compute value, P/L and weights (default true)"})
    def portfolio_snapshot(ctx: ToolContext, with_prices: bool = True) -> dict:
        """Current holdings rebuilt from Revolut statement exports and holdings.csv, with value, P/L and weights,
        plus the owner's watchlist (watchlist.txt)."""
        folder = trading_dir(ctx)
        positions = load_positions(folder)
        watchlist = load_watchlist(folder)
        if not positions:
            return {"positions": [], "watchlist": watchlist,
                    "note": f"No holdings found. Put Revolut statement CSVs or holdings.csv in {folder}."}
        rows = []
        for p in positions:
            row = {**asdict(p), "avg_cost": round(p.avg_cost, 4)}
            if with_prices:
                try:
                    closes = fetch_closes(p.ticker, fetch)
                    row["price"] = closes[-1] if closes else None
                except (OSError, ValueError):
                    row["price"] = None
                if row["price"]:
                    row["value"] = round(row["price"] * p.shares, 2)
                    row["pl_pct"] = round((row["price"] / p.avg_cost - 1) * 100, 2) if p.avg_cost else None
            rows.append(row)
        total = sum(r.get("value", 0) for r in rows)
        profile = load_profile(folder)
        for r in rows:
            if total and r.get("value"):
                r["weight_pct"] = round(r["value"] / total * 100, 2)
        over = [f"{r['ticker']} is {r['weight_pct']}% (limit {profile['max_position_pct']}%)"
                for r in rows if r.get("weight_pct", 0) > profile["max_position_pct"]]
        return {"positions": rows, "total_value": round(total, 2), "concentration_warnings": over,
                "watchlist": watchlist}

    @reg.tool(params={"tickers": "Tickers, e.g. ['NVDA', 'MSFT']"})
    def technical_signals(tickers: list[str]) -> dict:
        """Daily technicals per ticker: 1d/5d/1m/3m change, SMA50/200, RSI14, trend, distance from 52-week high/low."""
        out = {}
        for t in tickers[:25]:
            try:
                out[t.upper()] = technicals(fetch_closes(t, fetch))
            except (OSError, ValueError) as exc:
                out[t.upper()] = {"error": f"price data unavailable ({type(exc).__name__})"}
        return out

    @reg.tool(params={"tickers": "Tickers to check (max 10)"})
    def smart_money_signals(ctx: ToolContext, tickers: list[str]) -> dict:
        """Recent politician (Congress) trades, insider trades and 13F institutional holdings per ticker (Quiver Quant)."""
        token = os.environ.get("QUIVER_API_TOKEN", "")
        if not token:
            return {"error": "QUIVER_API_TOKEN is not set; politician/insider/13F signals unavailable. "
                             "Get a key at https://www.quiverquant.com and add it to .env."}
        endpoints = load_profile(trading_dir(ctx)).get("quiver", {})
        return {t.upper(): smart_money(t, token, endpoints, fetch) for t in tickers[:10]}

    @reg.tool(params={"ticker": "Ticker", "action": "buy or sell", "pct_of_portfolio": "Size as % of the portfolio",
                      "speculative": "True for a speculative / high-risk idea"})
    def check_trade_idea(ctx: ToolContext, ticker: str, action: str, pct_of_portfolio: float,
                         speculative: bool = False) -> dict:
        """Check a trade idea against the owner's position limits. Analysis only: nothing is ever executed."""
        folder = trading_dir(ctx)
        profile = load_profile(folder)
        snap = portfolio_snapshot(ctx)
        current = sum(r.get("weight_pct", 0) for r in snap.get("positions", []) if r["ticker"] == ticker.upper())
        result = check_idea(profile, action, float(pct_of_portfolio), current, speculative)
        return {"ticker": ticker.upper(), "action": action, **result}
