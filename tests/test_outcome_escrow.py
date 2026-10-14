"""Tiers as today's fixed-amount orders, both parties' signatures, the draft, and the command line."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from knos.outcomes import draft, escrow, sign, synth
from knos.outcomes.spec import micro, problems, spec_hash, terms_bytes
from knos.settle.v2 import pay

BUYER = Keypair.from_seed(bytes([1]) * 32)
SELLER = Keypair.from_seed(bytes([2]) * 32)
MINT = Keypair.from_seed(bytes([3]) * 32).pubkey()


def spec():
    return synth.example_spec(funder=str(BUYER.pubkey()), seller=str(SELLER.pubkey()), mint=str(MINT), seq_start=40)


def test_one_order_per_tier_at_the_escrows_own_addresses():
    s = spec()
    rows = escrow.orders(s)
    assert [o["seq"] for o in rows] == [40, 41, 42]
    for k, o in enumerate(rows):
        assert o["address"] == str(pay.order_pda(pay.scope_of(1401439243, 1), BUYER.pubkey(), 40 + k))
        assert o["fee"] == pay.order_fee(o["amount"])
    assert len({o["address"] for o in rows}) == 3


def test_the_escrowed_total_is_the_cap_plus_the_fees_and_never_more_than_the_cap_is_payable():
    s = spec()
    e = escrow.escrowed(s)
    assert sum(e["amounts"]) == e["cap"] == micro(30.0)
    assert e["total"] == micro(30.0) + sum(pay.order_fee(a) for a in e["amounts"])


def test_funding_builds_one_fund_order_wallet_per_tier_pinned_to_prove_yml_at_the_commit():
    s, sha = spec(), "c" * 40
    tok = pay.ata(BUYER.pubkey(), MINT)
    ixs = escrow.fund_ixs(s, sha, BUYER.pubkey(), tok, MINT)
    assert len(ixs) == 3
    for k, ix in enumerate(ixs):
        want = pay.fund_order_wallet_ix(BUYER.pubkey(), tok, MINT, 1401439243, 1, pay.units(micro(s["tiers"][k]["amount"])), "drexthealpha/knos-e2e",
                                        sha, terms_bytes(s, k), pay.MERGE, s["escrow"]["work_seconds"], 40 + k)
        assert bytes(ix.data) == bytes(want.data) and ix.accounts == want.accounts
        assert ix.accounts[1].pubkey == Pubkey.from_string(escrow.orders(s)[k]["address"])


def test_funding_refuses_a_deadline_inside_the_dispute_window():
    s = spec()
    from knos.outcomes.spec import utc
    end = utc(s["window"]["end"])
    s["escrow"]["work_seconds"] = 3 * 86_400                  # the spec's dispute window is 7 days
    with pytest.raises(ValueError, match="dispute_window_days"):
        escrow.fund_ixs(s, "c" * 40, BUYER.pubkey(), pay.ata(BUYER.pubkey(), MINT), MINT, now=end - 3600)
    s["dispute_window_days"] = 0
    assert len(escrow.fund_ixs(s, "c" * 40, BUYER.pubkey(), pay.ata(BUYER.pubkey(), MINT), MINT, now=end - 3600)) == 3


def test_funding_refuses_another_wallet_or_mint_and_mainnet():
    s = spec()
    with pytest.raises(ValueError):
        escrow.fund_ixs(s, "c" * 40, SELLER.pubkey(), pay.ata(SELLER.pubkey(), MINT), MINT)
    s["escrow"]["cluster"] = "mainnet-beta"
    with pytest.raises(ValueError):
        escrow.fund_ixs(s, "c" * 40, BUYER.pubkey(), pay.ata(BUYER.pubkey(), MINT), MINT)


def test_both_parties_sign_the_hash_and_nothing_else_verifies(tmp_path):
    s = spec()
    path = tmp_path / "outcome.signatures.json"
    with pytest.raises(ValueError):
        sign.sign(s, "buyer", SELLER)                      # the buyer signs with the funding wallet only
    sign.add(path, s, sign.sign(s, "buyer", BUYER))
    assert sign.verify(s, json.loads(path.read_text())) == ["no valid seller signature"]
    doc = sign.add(path, s, sign.sign(s, "seller", SELLER))
    assert sign.verify(s, doc) == []
    other = spec()
    other["tiers"][0]["min_lift"] = 0.06
    assert any("hashes to" in p for p in sign.verify(other, doc))
    forged = json.loads(json.dumps(doc))
    forged["signatures"][0]["signature"] = str(SELLER.sign_message(sign.message(spec_hash(s))))
    assert sign.verify(s, forged)
    text = sign.comment(s, doc, escrow.orders(s))
    assert spec_hash(s) in text and "SYNTHETIC" in text and escrow.orders(s)[2]["address"] in text


def test_the_draft_from_a_template_holds_and_needs_no_network(tmp_path):
    s = spec()
    sample = tmp_path / "tickets.csv"
    sample.write_text(synth.to_csv(synth.tickets(s, 60, seed=1)), encoding="utf-8")
    text, got, how = draft.draft("Our AI agent should resolve more support tickets without a human", sample, synthetic=True,
                                 now=datetime(2026, 10, 13, tzinfo=timezone.utc))
    assert how == "template" and problems(got) == []
    assert "EDIT" in text and "SYNTHETIC" in text
    assert got["metric"]["formula"] == "1 if status == 'solved' and escalated == 0 and reopened == 0 else 0"
    assert got["data"]["id_field"] == "ticket_id" and got["data"]["time_field"] == "created_at"
    assert got["window"]["start"] == "2026-10-20T00:00:00Z"


@pytest.mark.parametrize("goal,template", [("cut the time to first reply", "time"), ("more trial users convert to paid", "conversion"),
                                           ("raise revenue per order", "value"), ("make the thing better", "generic")])
def test_the_goal_picks_a_template(goal, template):
    assert draft.pick_template(goal) == template


def test_the_llm_draft_needs_the_flag_and_the_users_own_key(tmp_path):
    sample = tmp_path / "s.csv"
    sample.write_text(synth.to_csv(synth.tickets(spec(), 40, seed=2)), encoding="utf-8")
    with pytest.raises(ValueError, match="your own key"):
        draft.draft("resolve tickets", sample, llm=True, key_env="NOPE_KEY", env={})


def test_the_command_line(tmp_path, capsys):
    from knos import cli
    from knos.outcomes import yamlish
    s = spec()
    p = tmp_path / "outcome.yaml"
    p.write_text(yamlish.dumps(s), encoding="utf-8")
    assert cli.main(["outcome", "validate", str(p)]) == 0 and spec_hash(s) in capsys.readouterr().out
    assert cli.main(["outcome", "hash", str(p)]) == 0 and capsys.readouterr().out.strip() == spec_hash(s)
    assert cli.main(["outcome", "tiers", str(p), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["orders"] == escrow.orders(s)
    lock = tmp_path / "outcome.lock.json"
    assert cli.main(["outcome", "lock", str(p), "--out", str(lock)]) == 0
    assert json.loads(lock.read_text())["spec_hash"] == spec_hash(s)
    data = tmp_path / "tickets.csv"
    data.write_text(synth.to_csv(synth.tickets(s, 3000, seed=4)), encoding="utf-8")
    res = tmp_path / "result.json"
    rc = cli.main(["outcome", "measure", str(p), "--lock", str(lock), "--data", str(data), "--out", str(res)])
    out = json.loads(res.read_text())
    assert rc == (0 if out["passed"] else 1) and out["data"]["in_window"] == 3000
    capsys.readouterr()
    assert cli.main(["outcome", "audiences", str(res)]) == 0
    lines = capsys.readouterr().out.split()
    assert lines == [t["audience"] for t in out["tiers"] if t["passed"]]
    bad = tmp_path / "bad.yaml"
    bad.write_text(yamlish.dumps({**s, "version": 2}), encoding="utf-8")
    assert cli.main(["outcome", "validate", str(bad)]) == 2
