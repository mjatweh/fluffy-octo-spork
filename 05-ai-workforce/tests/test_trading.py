import json
import shutil
from pathlib import Path

import pytest

from workforce import trading
from workforce.registry import ToolRegistry
from workforce.tools import build_registry

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "trading"


def price_csv(closes):
    rows = "\n".join(f"2026-01-{i % 28 + 1:02d},{c},{c},{c},{c},1000" for i, c in enumerate(closes))
    return "Date,Open,High,Low,Close,Volume\n" + rows


def fake_fetch(prices, quiver=None, calls=None):
    def fetch(url, headers):
        if calls is not None:
            calls.append((url, headers))
        if "stooq" in url:
            sym = url.split("s=")[1].split("&")[0].split(".")[0].upper()
            if sym not in prices:
                raise OSError("no data")
            return price_csv(prices[sym])
        return json.dumps((quiver or {}).get(url.split("/beta")[1], []))
    return fetch


def test_parse_revolut_average_cost_and_ignores_cash_and_dividends():
    positions = trading.parse_revolut((EXAMPLES / "revolut-statement.example.csv").read_text())
    by = {p.ticker: p for p in positions}
    assert set(by) == {"AAPL", "AMD"}
    assert by["AAPL"].shares == 6 and by["AAPL"].cost_basis == 1380.0  # 2300 * 6/10 after selling 4
    assert by["AMD"].avg_cost == 150.0


def test_revolut_split_and_full_exit():
    text = ("Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate\n"
            "2026-01-01,NVDA,BUY - MARKET,2,USD 1000,\"USD 2,000.00\",USD,1\n"
            "2026-02-01,NVDA,STOCK SPLIT,18,,,USD,1\n"
            "2026-03-01,TSLA,BUY - MARKET,1,USD 200,USD 200,USD,1\n"
            "2026-04-01,TSLA,SELL - MARKET,1,USD 250,USD 250,USD,1\n")
    (nvda,) = trading.parse_revolut(text)
    assert nvda.shares == 20 and nvda.cost_basis == 2000.0 and nvda.avg_cost == 100.0


def test_load_positions_merges_revolut_and_holdings(tmp_path):
    for f in ("revolut-statement.example.csv", "holdings.example.csv"):
        shutil.copy(EXAMPLES / f, tmp_path / f)
    accounts = {(p.account, p.ticker) for p in trading.load_positions(tmp_path)}
    assert accounts == {("Revolut", "AAPL"), ("Revolut", "AMD"), ("Autopilot", "NVDA"), ("Autopilot", "MSFT")}


def test_indicators():
    up = [100 + i for i in range(260)]
    t = trading.technicals(up)
    assert t["trend"] == "uptrend" and t["rsi14"] == 100.0 and t["from_52w_high_pct"] == 0.0
    assert t["sma50"] == sum(up[-50:]) / 50 and t["change_1d_pct"] == round((359 / 358 - 1) * 100, 2)
    assert trading.rsi([1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1]) == 50.0
    assert trading.technicals([5.0])["sma200"] is None


def test_check_idea_limits():
    profile = {**trading.DEFAULT_PROFILE, "max_position_pct": 10, "max_speculative_pct": 20}
    ok = trading.check_idea(profile, "buy", 3, current_pct=5)
    assert ok["within_limits"] and ok["position_after_pct"] == 8
    too_big = trading.check_idea(profile, "buy", 8, current_pct=5)
    assert not too_big["within_limits"] and "limit is 10" in too_big["warnings"][0]
    spec = trading.check_idea(profile, "buy", 5, speculative=True, speculative_pct_now=18)
    assert "speculative bucket" in spec["warnings"][0]


@pytest.fixture
def trading_ctx(make_ctx, tmp_path, monkeypatch):
    folder = tmp_path / "ws" / "trading"
    folder.mkdir(parents=True)
    shutil.copy(EXAMPLES / "holdings.example.csv", folder / "holdings.csv")
    (folder / "profile.toml").write_text('risk_tolerance = "aggressive"\nmax_position_pct = 40.0\n')
    return make_ctx()


def registry_with(fetch):
    reg = ToolRegistry()
    trading.register_trading_tools(reg, fetch=fetch)
    return reg


def test_portfolio_snapshot_values_and_concentration(trading_ctx):
    reg = registry_with(fake_fetch({"NVDA": [100.0] * 5 + [150.0], "MSFT": [400.0]}))
    snap = reg.get("portfolio_snapshot")(trading_ctx)
    by = {r["ticker"]: r for r in snap["positions"]}
    assert by["NVDA"]["value"] == 1800.0 and by["MSFT"]["value"] == 1600.0
    assert snap["total_value"] == 3400.0 and by["NVDA"]["pl_pct"] == round((150 / (1450 / 12) - 1) * 100, 2)
    assert snap["concentration_warnings"] == ["NVDA is 52.94% (limit 40.0%)", "MSFT is 47.06% (limit 40.0%)"]
    assert reg.get("risk_profile")(trading_ctx)["risk_tolerance"] == "aggressive"


def test_watchlist_in_snapshot(trading_ctx, tmp_path):
    (tmp_path / "ws" / "trading" / "watchlist.txt").write_text("pltr, amd\n# comment\nPLTR tsm\n")
    snap = registry_with(fake_fetch({"NVDA": [1.0], "MSFT": [1.0]})).get("portfolio_snapshot")(trading_ctx)
    assert snap["watchlist"] == ["PLTR", "AMD", "TSM"]


def test_snapshot_without_data_explains(make_ctx):
    snap = registry_with(fake_fetch({})).get("portfolio_snapshot")(make_ctx())
    assert snap["positions"] == [] and "Revolut statement CSVs" in snap["note"]


def test_technical_signals_handles_missing_ticker(make_ctx):
    reg = registry_with(fake_fetch({"AAPL": [float(i) for i in range(1, 80)]}))
    out = reg.get("technical_signals")(make_ctx(), tickers=["aapl", "ZZZZ"])
    assert out["AAPL"]["last"] == 79.0 and "error" in out["ZZZZ"]


def test_smart_money_requires_token_then_queries_quiver(trading_ctx, monkeypatch):
    calls = []
    quiver = {"/historical/congresstrading/NVDA": [{"Representative": "A", "Transaction": "Purchase"}] * 12}
    reg = registry_with(fake_fetch({}, quiver, calls))
    assert "QUIVER_API_TOKEN" in reg.get("smart_money_signals")(trading_ctx, tickers=["NVDA"])["error"]
    monkeypatch.setenv("QUIVER_API_TOKEN", "secret")
    out = reg.get("smart_money_signals")(trading_ctx, tickers=["nvda"])
    assert len(out["NVDA"]["congress"]) == 10 and out["NVDA"]["insiders"] == []
    assert calls[0][1]["Authorization"] == "Token secret"


def test_check_trade_idea_uses_current_weight(trading_ctx):
    reg = registry_with(fake_fetch({"NVDA": [150.0], "MSFT": [400.0]}))
    res = reg.get("check_trade_idea")(trading_ctx, ticker="NVDA", action="buy", pct_of_portfolio=5)
    assert not res["within_limits"] and res["position_after_pct"] == pytest.approx(57.94, abs=0.01)


def test_no_trade_execution_tools_exist():
    names = {t.name for t in build_registry()}
    assert not any(w in n for n in names for w in ("order", "execute", "place", "buy", "sell"))


def test_trading_analyst_in_roster(config):
    agent = config.agents["trading_analyst"]
    assert {"portfolio_snapshot", "check_trade_idea", "smart_money_signals"} <= set(agent.tools)
    assert "send_message" not in agent.tools
