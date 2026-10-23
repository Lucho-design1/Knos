"""The revenue data (knos.money.revenue): revenue is 0 and says why; the measured part is what the chain held or says it
was not read; the model is labelled a model and its inputs start at 0 and give 0; docs/reference/MONEY.md agrees with the
config. The revenue page and its data files are no longer published in web/."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from knos.money import fees_config, revenue

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


@pytest.fixture(scope="module")
def cfg():
    return fees_config.load()


def test_a_model_with_no_inputs_is_zero_and_says_it_is_a_model(cfg):
    m = revenue.model({}, cfg)
    assert m["month_total"] == "0.00" and set(m["month"].values()) == {"0.00"} and m["label"].startswith("MODEL") and "lower bound" in m["label"]
    assert all(v == 0 for k, v in m["inputs"].items() if k != "cloud_subscribers")
    assert m["status"]["cloud"] == "decided" and m["status"]["payout"] == "live" and m["status"]["bounty_platform"] == "decided"


def test_the_model_is_the_config_times_the_inputs(cfg):
    m = revenue.model({"verifications": 100_500, "payout_volume_usd": 1_000_000, "payouts": 10, "bounty_volume_usd": 100_000,
                       "lab_order_volume_usd": 50_000, "graduation_volume_usd": 200_000,
                       "task_package_sales_usd": 10_000, "cloud_subscribers": {"Starter": 3, "Team": 1}}, cfg)
    # the bounty and lab order lines are the off-chain rest (5% - 0.30%, 3% - 0.30%): the payout line holds the on-chain part
    assert m["month"] == {"verification": "1.00", "payout": "3000.00", "bounty_platform": "4700.00", "lab_order": "1350.00",
                          "graduation": "1000.00", "task_package": "1000.00", "cloud": "260.00"}
    assert m["month_total"] == "11311.00" and m["year_total"] == "135732.00"
    # the floor per release wins for many small releases
    assert revenue.model({"payout_volume_usd": 100, "payouts": 100}, cfg)["month"]["payout"] == "5.00"
    with pytest.raises(ValueError):
        revenue.model({"cloud_subscribers": {"Gold": 1}}, cfg)


def test_revenue_is_zero_and_an_unread_chain_says_so(cfg):
    d = revenue.build(None, None, cfg, now=datetime(2026, 10, 13, tzinfo=timezone.utc))
    assert d["revenue"]["usd"] == "0" and "devnet" in d["revenue"]["why"]
    assert d["treasury"]["read"] is False and all(a["balance"] is None for a in d["treasury"]["accounts"]) and d["treasury"]["test_money_held"] is None
    assert d["graduation_demo"] is None


def test_the_revenue_page_is_not_published():
    for name in ("revenue_data.json", "revenue_devnet.json", "revenue.js", "revenue/index.html"):
        assert not (WEB / name).exists(), name


def test_the_money_page_states_the_configs_numbers_and_sources(cfg):
    doc = (ROOT / "docs" / "reference" / "MONEY.md").read_text(encoding="utf-8")
    assert "config/fees.yaml" in doc and "placeholder" in doc.lower() and "decided" in doc.lower() and "program upgrade" in doc
    for t in cfg.credit_tiers:
        assert f"| {t['name']} | {t['usd_month']} | {t['credit_usd_month']} |" in doc
    for line in ("| bounty fee | 5% of the bounty", "| lab order | 3% of the order", "| x402 check | 0.02 USD each"):
        assert line in doc, line
    for role, bps in cfg.roles.items():
        assert f"| {role} | {bps} |" in doc
    assert "MONEY.md" in (ROOT / "docs" / "reference" / "README.md").read_text(encoding="utf-8")
