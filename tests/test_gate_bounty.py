"""Bounties mode: claims, the winner (passed at the merged head and merged first), the fee from the one fee config,
and the treasury the fee lands in (Knos's Squads vault)."""
from __future__ import annotations

import sys
import types

from knos.gate import bounty
from knos.settle.v2 import pay


def test_claims():
    assert bounty.claims({"title": "Fix slug", "body": "Fixes #12 and closes: #13\nresolves #12"}) == [12, 13]
    assert bounty.claims({"title": "x", "body": "see #12"}) == []


def test_must_close_only_in_bounties_mode_for_a_failing_claim():
    on = {"bounties": {"enabled": True}}
    claim = {"body": "Fixes #3"}
    assert bounty.must_close(on, claim, {"passed": False})
    assert not bounty.must_close(on, claim, {"passed": True})
    assert not bounty.must_close({"bounties": {"enabled": False}}, claim, {"passed": False})
    assert not bounty.must_close(on, {"body": "no claim"}, {"passed": False})


def test_winner_is_the_first_merged_claim_that_passed_at_its_head():
    pulls = [
        {"number": 1, "body": "Fixes #5", "merged_at": "2026-10-13T10:00:00Z", "head": {"sha": "a" * 40}},
        {"number": 2, "body": "Fixes #5", "merged_at": "2026-10-13T11:00:00Z", "head": {"sha": "b" * 40}},
        {"number": 3, "body": "Fixes #5", "merged_at": None, "head": {"sha": "c" * 40}},
    ]
    verdicts = {1: {"passed": True, "head": "0" * 40}, 2: {"passed": True, "head": "b" * 40}, 3: {"passed": True, "head": "c" * 40}}
    assert bounty.winner(5, pulls, verdicts)["number"] == 2          # #1 passed at another commit, #3 is not merged
    assert bounty.winner(6, pulls, verdicts) is None


def test_quote_falls_back_to_the_programs_numbers(monkeypatch):
    monkeypatch.setitem(sys.modules, "knos.money", None)
    q = bounty.quote(20_000_000, "job")
    assert q["fee"] == pay.order_fee(20_000_000) == 60_000 and q["payee_gets"] == 19_940_000 and "compiled" in q["source"]
    q = bounty.quote(1_000_000, "order")
    assert q["fee"] == 50_000 and q["funder_pays"] == 1_050_000 and q["treasury_owner"] == str(pay.FEE_OWNER)


def test_quote_reads_the_one_fee_config_when_installed(monkeypatch):
    fake = types.ModuleType("knos.money.fees_config")
    fake.load = lambda: types.SimpleNamespace(bounty=lambda amount: {"amount": amount, "fee": 123, "fee_to": "treasury"})
    pkg = types.ModuleType("knos.money")
    pkg.fees_config = fake
    monkeypatch.setitem(sys.modules, "knos.money", pkg)
    monkeypatch.setitem(sys.modules, "knos.money.fees_config", fake)
    q = bounty.quote(5_000_000, "order")
    assert q["fee"] == 123 and q["funder_pays"] == 5_000_123 and "fees.yaml" in q["source"]


def test_treasury_is_the_squads_vaults_fee_account():
    t = bounty.treasury(str(pay.USDC_DEVNET))
    assert t["fee_owner"] == "4G3cznCnwCUPBCZwzKiLupjdgB5pSoCcGWNGuFv4TYFo"
    assert t["fee_account_0"] == str(pay.ata(pay.FEE_OWNER, pay.USDC_DEVNET))
