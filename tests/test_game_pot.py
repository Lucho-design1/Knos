"""The game's pooled pot: the division rule from config/fees.yaml, the split by the referee's verdicts, the pot as
private knos_pay orders, and the payout of several funders' orders to the winners in LiteSVM (the test build)."""
from __future__ import annotations

import pytest

from knos.game import pot
from knos.money import fees_config
from knos.settle.v2 import pay


def _final(*lifts, failed=0):
    vs = [{"player": f"p{i}", "name": f"n{i}", "passed": True, "lift": lift, "rank": i + 1} for i, lift in enumerate(lifts)]
    vs += [{"player": f"x{i}", "name": f"x{i}", "passed": False, "lift": None} for i in range(failed)]
    return {"verdicts": vs}


def test_the_rule_is_the_fee_configs_placeholder_line():
    r = pot.rule()
    cfg = fees_config.load()
    assert r["winner_bps"] + r["partial_bps"] == 10_000 and 1 <= r["max_paid"] <= pay.MAX_PAYEES
    assert r["status"] == "placeholder" == cfg.doc["game_pot"]["status"]   # the founder sets the numbers


def test_the_split_follows_the_verdicts():
    assert pot.split(None)["payable"] is False
    nobody = pot.split(_final(failed=2))
    assert nobody["payable"] is False and "back to its funder" in nobody["why"]
    alone = pot.split(_final(0.3, failed=1))
    assert [(p["player"], p["bps"]) for p in alone["parts"]] == [("p0", 10_000)]
    s = pot.split(_final(0.4, 0.3, 0.1))
    bps = [p["bps"] for p in s["parts"]]
    assert sum(bps) == 10_000 and bps[0] >= 7000 and bps[1] == 3000 * 3 // 4 and bps[2] == 3000 // 4
    many = pot.split(_final(0.5, 0.4, 0.3, 0.2, 0.1))
    assert len(many["parts"]) == 4 and sum(p["bps"] for p in many["parts"]) == 10_000   # one order pays at most 4
    got = pot.amounts(10_000_003, s["parts"])
    assert sum(got) == 10_000_003


def test_fees_on_a_pot_are_the_payout_fee_on_chain_and_the_bounty_fee():
    f = pot.fees(100_000_000)
    cfg = fees_config.load()
    assert f["payout_fee_onchain"] == cfg.fee("payout", 100_000_000)
    assert f["bounty_platform"]["fee"] == cfg.platform("bounty_platform", 100_000_000)["fee"]


def test_the_pot_is_a_private_scope_anyone_can_find_from_the_game_id():
    p = pot.plan("g1", "ab" * 32, 1401439243)
    assert p["scope"] == pay.scope_of(1401439243, 0, pot.salt("g1")).hex() != pot.plan("g2", "ab" * 32, 1401439243)["scope"]
    assert '"kind":"game_pot"' in p["terms"] and p["terms_hash"] == pay.terms_hash(p["terms"].encode()).hex()
    from solders.keypair import Keypair
    k = Keypair()
    with pytest.raises(pot.PotError):
        pot.fund_ix(p, k.pubkey(), k.pubkey(), k.pubkey(), pay.ORDER_MIN_AMOUNT - 1)
    ix = pot.fund_ix(p, k.pubkey(), k.pubkey(), k.pubkey(), pay.ORDER_MIN_AMOUNT)
    assert ix.accounts[1].pubkey == pot.order_address(p, k.pubkey())
    with pytest.raises(pot.PotError):
        pot.plan("g1", "ab" * 32, 0)


def test_the_pot_pays_the_winners_in_litesvm(tmp_path):
    pytest.importorskip("solders.litesvm")
    from pathlib import Path

    from solders.keypair import Keypair
    root = Path(__file__).resolve().parents[1]
    p = pot.plan("g-pay", "cd" * 32, 31_415_926)
    s = pot.split(_final(0.4, 0.2))
    wallets = [str(Keypair().pubkey()) for _ in s["parts"]]
    payees = [(1000 + i, part["bps"], w) for i, (part, w) in enumerate(zip(s["parts"], wallets))]
    funders = [Keypair(), Keypair()]
    got = pot.pay_litesvm(root, p, [{"amount": 20_000_000, "key": funders[0]}, {"amount": 5_000_000, "key": funders[1]}], payees)
    assert got["paid"], got.get("error")
    assert [o["order"] for o in got["orders"]] == [str(pot.order_address(dict(p), f.pubkey())) for f in funders]   # the devnet addresses
    each = [pot.amounts(20_000_000, s["parts"]), pot.amounts(5_000_000, s["parts"])]
    assert [x["received"] for x in got["payees"]] == [a + b for a, b in zip(*each)]
    assert all(o["order_closed"] for o in got["orders"]) and got["label"].startswith("LiteSVM")
