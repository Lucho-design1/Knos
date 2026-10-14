"""The revenue dashboard: revenue is 0 and says why; the measured part is what the chain held or says it was not read;
the model is labelled a model, its inputs start at 0 and give 0, and the page's JavaScript computes what Python does;
the committed data files hold no key and no figure without its source; docs/reference/MONEY.md agrees with the config."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
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


def test_the_billion_is_arithmetic_on_the_rates(cfg):
    b = revenue.one_billion(cfg)
    assert b["label"].startswith("DERIVED") and "not a forecast" in b["label"]
    assert int(b["payout_volume_usd_year"]) * cfg.doc["fees"]["payout"]["rate_bps"] // 10_000 == pytest.approx(10 ** 9, abs=1)
    assert b["placeholders_used"] == [] and any(p.startswith("cloud.tiers.Team = 200") for p in b["decided_used"])
    assert int(b["bounty_volume_usd_year"]) * 500 // 10_000 == pytest.approx(10 ** 9, abs=1)


def test_revenue_is_zero_and_an_unread_chain_says_so(cfg):
    d = revenue.build(None, WEB / "revenue_devnet.json", cfg, now=datetime(2026, 10, 13, tzinfo=timezone.utc))
    assert d["revenue"]["usd"] == "0" and "devnet" in d["revenue"]["why"]
    assert d["treasury"]["read"] is False and all(a["balance"] is None for a in d["treasury"]["accounts"]) and d["treasury"]["test_money_held"] is None


@pytest.mark.parametrize("name", ["revenue_data.json", "revenue_devnet.json"])
def test_the_committed_data_is_public_and_labelled(name, cfg):
    raw = (WEB / name).read_text(encoding="utf-8")
    d = json.loads(raw)
    assert not re.search(r"\[\s*\d+\s*(,\s*\d+\s*){63}\]", raw), "a 64-byte key array"
    assert "BEGIN" not in raw and "secret" not in raw.lower()
    if name == "revenue_data.json":
        assert d["revenue"]["usd"] == "0" and d["schedule"]["fees"] == cfg.doc["fees"] and d["model"]["month_total"] == "0.00"
        assert d["graduation_demo"]["synthetic"] is True
    else:
        assert d["synthetic"] is True and d["cluster"] == "devnet" and "SYNTHETIC" in d["what"]
        assert all(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,88}", s["signature"]) for s in d["signatures"])
        assert all(s["explorer"].endswith("?cluster=devnet") for s in d["signatures"])


def test_the_page_draws_from_the_data_with_text_only():
    page = (WEB / "revenue" / "index.html").read_text(encoding="utf-8")
    js = (WEB / "revenue.js").read_text(encoding="utf-8")
    assert "../revenue_data.json" in page and "MODEL, not a forecast" in page and "Revenue: 0 USD" in page
    assert "innerHTML" not in js and "eval(" not in js


def test_the_page_model_is_the_python_model(cfg, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("no node: the page's model is not run")
    inputs = {"verifications": 123_456, "payout_volume_usd": 77_777, "payouts": 3, "bounty_volume_usd": 12_345, "lab_order_volume_usd": 6_789, "graduation_volume_usd": 9_999,
              "task_package_sales_usd": 2_000, "cloud_subscribers": {"Starter": 2, "Pro": 1, "Team": 0}}
    script = tmp_path / "m.mjs"
    script.write_text(f"import {{ model }} from {json.dumps((WEB / 'revenue.js').as_uri())};\n"
                      f"console.log(JSON.stringify(model({json.dumps(inputs)}, {json.dumps(cfg.public())})));\n", encoding="utf-8")
    run = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60, check=True)
    js = json.loads(run.stdout)
    py = revenue.model(inputs, cfg)
    assert js["month"] == py["month"] and js["month_total"] == py["month_total"]


def test_the_money_page_states_the_configs_numbers_and_sources(cfg):
    doc = (ROOT / "docs" / "reference" / "MONEY.md").read_text(encoding="utf-8")
    assert "config/fees.yaml" in doc and "placeholder" in doc.lower() and "decided" in doc.lower() and "program upgrade" in doc
    assert "TechCrunch" in doc and "7 Oct 2026" in doc and "unaudited" in doc.lower()
    for t in cfg.credit_tiers:
        assert f"| {t['name']} | {t['usd_month']} | {t['credit_usd_month']} |" in doc
    for line in ("| bounty fee | 5% of the bounty", "| lab order | 3% of the order", "| x402 check | 0.02 USD each"):
        assert line in doc, line
    for role, bps in cfg.roles.items():
        assert f"| {role} | {bps} |" in doc
    assert "MONEY.md" in (ROOT / "docs" / "reference" / "README.md").read_text(encoding="utf-8")
