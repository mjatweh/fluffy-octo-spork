import shutil
from email.message import EmailMessage
from pathlib import Path

import pytest

from workforce import deals
from workforce.registry import ToolRegistry

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "deals"


def test_irr_and_moic():
    r = deals.returns([-1000, 100, 100, 1100])
    assert r["irr_pct"] == pytest.approx(10.0, abs=0.01) and r["moic"] == 1.3 and r["profit"] == 300
    assert deals.irr([1000, 100]) is None and deals.irr([]) is None


def test_real_estate_example_listing():
    m = deals.real_estate(price=6_200_000, noi=434_000, loan_pct=65, rate_pct=6.75, amort_years=25)
    assert m["cap_rate_pct"] == 7.0 and m["loan"] == 4_030_000
    assert m["annual_debt_service"] == pytest.approx(334_100, rel=0.002)
    assert m["dscr"] == pytest.approx(1.30, abs=0.01) and m["cash_on_cash_pct"] == pytest.approx(4.35, abs=0.05)
    assert deals.real_estate(1_000_000, 70_000)["dscr"] is None  # all cash


def test_check_against_criteria():
    criteria = {"real_estate": {"min_cap_rate_pct": 6.5, "min_cash_on_cash_pct": 7.0, "max_check_size": 5e6,
                                "geography": "Southeast"}}
    res = deals.check_against(criteria, "real_estate", {"cap_rate_pct": 7.0, "cash_on_cash_pct": 4.35})
    assert res["fails"] == ["cash_on_cash_pct"] and res["missing"] == ["check_size"]
    assert not res["meets_criteria"] and res["notes"] == {"geography": "Southeast"}
    assert "no criteria" in deals.check_against(criteria, "venture", {})["note"]


def test_pipeline_upsert_and_roundtrip(tmp_path):
    path = tmp_path / "pipeline.csv"
    rows = deals.upsert([], {"name": "Riverside Flex", "asset_class": "real_estate", "source": "listing.md"})
    rows = deals.upsert(rows, {"id": "riverside-flex", "stage": "screening", "recommendation": "more info"})
    deals.write_pipeline(path, rows)
    (row,) = deals.read_pipeline(path)
    assert row["id"] == "riverside-flex" and row["stage"] == "screening" and row["source"] == "listing.md"
    with pytest.raises(ValueError, match="stage must be"):
        deals.upsert(rows, {"name": "X", "stage": "maybe"})


def test_read_eml(tmp_path):
    msg = EmailMessage()
    msg["From"], msg["Subject"] = "Broker <b@brokerage.com>", "New listing: Flex industrial"
    msg.set_content("Asking $6.2M, NOI $434k.")
    (tmp_path / "deal.eml").write_bytes(bytes(msg))
    text = deals.read_document(tmp_path / "deal.eml")
    assert "Subject: New listing" in text and "NOI $434k" in text


@pytest.fixture
def reg():
    r = ToolRegistry()
    deals.register_deal_tools(r)
    return r


@pytest.fixture
def ctx(make_ctx, tmp_path):
    folder = tmp_path / "ws" / "deals"
    (folder / "inbox").mkdir(parents=True)
    shutil.copy(EXAMPLES / "criteria.example.toml", folder / "criteria.toml")
    shutil.copy(EXAMPLES / "inbox-listing.example.md", folder / "inbox" / "riverside.md")
    return make_ctx()


def test_tools_end_to_end(reg, ctx, tmp_path):
    inbox = reg.get("deal_inbox")(ctx)
    assert inbox["files"] == [{"name": "riverside.md", "in_pipeline": False, "kb": inbox["files"][0]["kb"]}]
    assert "Asking price: $6,200,000" in reg.get("read_deal_document")(ctx, name="riverside.md")
    assert reg.get("deal_criteria")(ctx)["real_estate"]["min_dscr"] == 1.25
    check = reg.get("check_deal_criteria")(ctx, asset_class="real_estate",
                                           metrics={"cap_rate_pct": 7.0, "dscr": 1.3, "cash_on_cash_pct": 4.35,
                                                    "check_size": 2_300_000})
    assert check["fails"] == ["cash_on_cash_pct"]
    reg.get("update_pipeline")(ctx, name="Riverside Flex", source="riverside.md", stage="screening",
                               recommendation="more info")
    assert reg.get("deal_inbox")(ctx)["files"][0]["in_pipeline"] is True
    assert reg.get("deal_pipeline")(ctx)["counts"]["screening"] == 1
    saved = reg.get("save_deal_memo")(ctx, title="Riverside Flex", markdown="# Memo")
    assert (tmp_path / "ws" / "deals" / saved.removeprefix("saved ")).read_text() == "# Memo"


def test_read_deal_document_stays_in_inbox(reg, ctx, tmp_path):
    (tmp_path / "ws" / "deals" / "criteria.toml").write_text("secret = 1")
    with pytest.raises(ValueError, match="not a file in the deals inbox"):
        reg.get("read_deal_document")(ctx, name="../criteria.toml")


def test_deal_analyst_in_roster_without_outreach_tools(config):
    agent = config.agents["deal_analyst"]
    assert {"deal_inbox", "update_pipeline", "save_deal_memo"} <= set(agent.tools)
    assert not {"send_message", "run_sibling"} & set(agent.tools)
