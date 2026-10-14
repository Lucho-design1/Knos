"""config/fees.yaml, the one fee config: it loads, it says what the program and the price book say (a drift fails
here), its arithmetic is the program's, every placeholder is listed, and a bad file is refused line by line."""
from __future__ import annotations

import copy
import random
from decimal import Decimal
from pathlib import Path

import pytest

from knos import billing, fees, plan_floor
from knos.money import fees_config as fc
from knos.settle.v2 import pay

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "fees.yaml"


@pytest.fixture(scope="module")
def cfg():
    return fc.load(CONFIG)


def test_the_one_config_loads_and_mirrors_the_program_and_the_price_book(cfg):
    o, f = cfg.doc["onchain"], cfg.doc["fees"]
    assert (o["rate_bps"], fc.micro(o["floor_usd"]), o["max_payees"], fc.micro(o["order_min_usd"])) == (pay.FEE_BPS, pay.FEE_MIN, pay.MAX_PAYEES, pay.ORDER_MIN_AMOUNT)
    assert (fc.micro(o["relayer_tip_usd"]), fc.micro(o["relayer_tip_first_usd"]), o["plan_floor_bps"]) == (pay.TIP, pay.TIP_FIRST, plan_floor.FLOOR_BPS)
    assert cfg.doc["treasury"]["fee_owner"] == str(pay.FEE_OWNER)
    assert Decimal(f["verification"]["usd_each"]) == billing.METER_PRICE and f["verification"]["free_per_month"] == billing.METER_FREE
    assert Decimal(f["payout"]["rate_bps"]) / 10_000 == billing.ACCEPT_RATE and Decimal(f["payout"]["floor_usd"]) == billing.ACCEPT_FLOOR
    assert cfg.doc["revenue_today"] == "0" and cfg.doc["network"] == "solana devnet"


def test_payout_and_bounty_fees_are_exactly_the_programs(cfg):
    rng = random.Random(329)
    amounts = [0, 1, 5_000_000, 16_666_666, 16_666_667, 20_000_000, 10 ** 11] + [rng.randrange(10 ** 11) for _ in range(500)]
    for a in amounts:
        assert cfg.fee("payout", a) == cfg.fee("bounty", a) == pay.order_fee(a) == fees.NEW.order(a), a
    assert cfg.fee("funding", 10 ** 9) == 0
    assert cfg.bounty(20_000_000) == {"amount": 20_000_000, "fee": 60_000, "total": 20_060_000, "payer": "funder, on top of the amount",
                                      "fee_to": "treasury", "treasury": str(pay.FEE_OWNER), "status": "live"}


def test_count_lines_take_the_free_month_first_and_public_repos_pay_nothing(cfg):
    each = fc.micro(cfg.doc["fees"]["verification"]["usd_each"])
    free = cfg.doc["fees"]["verification"]["free_per_month"]
    assert cfg.price("verification", 10) == 0
    assert cfg.price("verification", 10, used=free - 4) == 6 * each
    assert cfg.price("verification", 10, used=free + 7) == 10 * each
    assert cfg.price("verification", 10 ** 6, used=free, public=True) == 0
    assert cfg.price("x402_check", 3) == 3 * each
    with pytest.raises(ValueError):
        cfg.fee("verification", 5)
    with pytest.raises(ValueError):
        cfg.price("payout", 5)
    with pytest.raises(ValueError):
        cfg.fee("nonsense", 5)


def test_the_split_and_the_task_package_add_up(cfg):
    for a in (0, 1, 7, 5_000_003, 99_999_999_999):
        got = cfg.split(a)
        assert sum(x for _, x in got) == a and [r for r, _ in got] == list(cfg.roles)
    tp = cfg.task_package(2_000 * 10 ** 6)
    assert tp["knos"] + tp["maintainer"] == 2_000 * 10 ** 6 and tp["status"] == "placeholder"


def test_every_placeholder_is_listed_and_marked(cfg):
    ph = cfg.placeholders()
    for needle in ("fees.graduation.rate_bps", "fees.task_package.knos_bps", "splits.roles.researcher", "cloud.tiers.Starter", "cloud.credit_usd"):
        assert any(p.startswith(needle) for p in ph), needle
    assert cfg.doc["cloud"]["status"] == "placeholder"
    assert all(cfg.doc["fees"][k]["status"] == "live" for k in ("payout", "bounty", "funding"))
    text = CONFIG.read_text(encoding="utf-8")
    assert "TechCrunch, 7 Oct 2026" in text and "WSJ" in text and "unaudited" in text and "Epoch AI, 12 Jan 2026" in text


def test_the_small_reader_reads_the_file_as_pyyaml_does():
    yaml = pytest.importorskip("yaml")
    text = CONFIG.read_text(encoding="utf-8")
    assert fc.parse_yaml(text) == yaml.safe_load(text)
    sample = 'a:\n  b: "x # not a comment"  # a comment\n  c:\n    - 1\n    - two\n  d:\n    - name: "n"\n      v: 3\n    - name: m\ne: null\n'
    assert fc.parse_yaml(sample) == yaml.safe_load(sample)
    for bad in ("a: 1\na: 2\n", "a:\n\tb: 1\n", "a: 1\n   b: 2\n"):
        with pytest.raises(ValueError):
            fc.parse_yaml(bad)


def _broken(cfg, change) -> list[str]:
    doc = copy.deepcopy(cfg.doc)
    change(doc)
    return fc.validate(doc)


@pytest.mark.parametrize("change, said", [
    (lambda d: d["onchain"].__setitem__("rate_bps", 25), "onchain.rate_bps"),
    (lambda d: d["onchain"].__setitem__("floor_usd", "0.04"), "onchain.floor_usd"),
    (lambda d: d["fees"]["bounty"].__setitem__("rate_bps", 10), "fees.bounty.rate_bps"),
    (lambda d: d["fees"]["bounty"].__setitem__("to", "the founder"), "fees.bounty.to"),
    (lambda d: d["fees"]["verification"].__setitem__("usd_each", "0.003"), "fees.verification.usd_each"),
    (lambda d: d["fees"]["verification"].__setitem__("public_repos_usd", "1"), "public_repos_usd"),
    (lambda d: d["fees"]["payout"].__setitem__("floor_usd", 0.05), "money is a quoted decimal string"),
    (lambda d: d["fees"]["graduation"].__setitem__("status", "maybe"), "fees.graduation.status"),
    (lambda d: d["fees"].pop("task_package"), "fees.task_package: missing"),
    (lambda d: d["splits"]["roles"].__setitem__("referee", 600), "add up to 10100"),
    (lambda d: d["splits"]["roles"].__setitem__("investor", 1), "splits.roles"),
    (lambda d: d["treasury"].__setitem__("fee_owner", "11111111111111111111111111111111"), "treasury.fee_owner"),
    (lambda d: d.__setitem__("revenue_today", "1000"), "revenue_today"),
    (lambda d: d.__setitem__("network", "solana mainnet"), "network"),
    (lambda d: d["sources"]["nous"].__setitem__("source", ""), "sources.nous"),
    (lambda d: d["sources"]["nous"].__setitem__("audited", True), "sources.nous"),
    (lambda d: d["cloud"]["tiers"].append({"name": "Pro", "usd_month": "5", "credits_month": 1}), "cloud.tiers"),
    (lambda d: d["cloud"]["tiers"][0].__setitem__("usd_month", "-20"), "cloud.tiers.Starter.usd_month"),
])
def test_a_config_that_drifts_is_refused(cfg, change, said):
    problems = _broken(cfg, change)
    assert any(said in p for p in problems), problems


def test_load_refuses_a_bad_file_and_honours_the_env(tmp_path, monkeypatch, cfg):
    bad = tmp_path / "fees.yaml"
    bad.write_text(CONFIG.read_text(encoding="utf-8").replace("  rate_bps: 30\n  floor_usd", "  rate_bps: 31\n  floor_usd", 1), encoding="utf-8")
    with pytest.raises(fc.FeeConfigError) as e:
        fc.load(bad)
    assert "onchain.rate_bps" in str(e.value)
    with pytest.raises(fc.FeeConfigError):
        fc.load(tmp_path / "missing.yaml")
    monkeypatch.setenv(fc.ENV, str(CONFIG))
    assert fc.load().doc == cfg.doc


def test_an_orders_own_rate_is_used_when_given(cfg):
    """Finding 42: an order pays the rate fixed at its funding (pay.Order.fee_bps), or an owner's Plan."""
    for a in (5_000_000, 20_000_000, 10 ** 10):
        for bps in (20, 25, 30):
            assert cfg.fee("payout", a, bps=bps) == pay.order_fee(a, bps)
    for bad in (10, 31, True, "20"):
        with pytest.raises(ValueError):
            cfg.fee("bounty", 20_000_000, bps=bad)
    with pytest.raises(ValueError):
        cfg.fee("graduation", 20_000_000, bps=20)
