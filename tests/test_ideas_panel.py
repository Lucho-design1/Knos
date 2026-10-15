"""A pull commitment's stages judged by a referee PANEL (knos_pay 0.3.34 test build, LiteSVM): the buyer locks each
stage pinning 2-of-3 referee keys; the oracle reads the public source (recorded fixture); a met stage is RELEASED to
the payee when two referees sign "stage met" over the oracle's evidence hash, and a missed stage is REFUNDED to the
buyer at once when two sign "stage missed". Synthetic test units; the referee keys are made per test."""
from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("solders.litesvm")

from solders.keypair import Keypair  # noqa: E402

from _order import USDC, OrderChain  # noqa: E402

from knos import ideas  # noqa: E402
from knos.ideas import IdeaError, K, sources, wanted as W  # noqa: E402
from knos.settle.v2 import pay  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "ideas" / "recorded-fixture.json"
BUILD = "knos_pay_v2_0334_test.so"
TRIAL = "NCT04718792"
ORC = "0000-0002-1825-0097"      # ORCID's public test record stands in for the researcher


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for k in ideas.ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no live API call in tests")))
    monkeypatch.setenv(ideas.FIXTURES_ENV, str(FIXTURE))


def tokens(c: OrderChain, account) -> int:
    d = c.data(account)
    return int.from_bytes(d[64:72], "little") if d and len(d) >= 72 else 0


def test_a_met_stage_is_released_by_two_of_three_verdicts_and_a_missed_stage_is_refunded():
    c = OrderChain(pay_build=BUILD)
    claim = sources.get(TRIAL)
    p = W.plan(claim, units=10, price=4)
    panel = [Keypair() for _ in range(3)]
    keys = [bytes(k.pubkey()) for k in panel]
    buyer, tok = c.wallet(c.usdc, 100 * USDC)
    for part in (K.stage1, K.stage2):
        assert c.send([W.fund_panel_ix(p, part, buyer.pubkey(), tok, c.usdc, 2, keys)], buyer, tag="idea_stage_panel_lock"), c.err
    s1, s2 = W.panel_address(p, K.stage1, buyer.pubkey()), W.panel_address(p, K.stage2, buyer.pubkey())
    met = W.check(claim, p[K.stage1][K.oracle])
    missed = W.check(claim, p[K.stage2][K.oracle])
    assert W.verdict_of(met) == W.PASS and W.verdict_of(missed) == W.FAIL
    payee = Keypair().pubkey()
    payees = [(ORC, 10_000, payee)]

    def one(order, ev, who):
        o = c.order(order)
        sig = W.sign_stage(who, order, o, ev, payees)
        return c.send(W.stage_verdict_ixs(c.payer.pubkey(), order, o, 2, keys, ev, payees, [sig]), mark=False)

    # stage 1 met: one referee is recorded, nothing moves; the second releases the stage to the payee
    assert one(s1, met, panel[0]), c.err
    assert c.order(s1).paid == 0
    assert one(s1, met, panel[2]), c.err
    assert c.order(s1) is None and tokens(c, pay.ata(payee, c.usdc)) == p[K.stage1][K.amount]
    # stage 2 missed: two FAIL verdicts refund the amount and its fee to the buyer now, before the deadline
    before = tokens(c, tok)
    o2 = c.order(s2)
    assert one(s2, missed, panel[1]), c.err
    assert one(s2, missed, panel[0]), c.err
    assert c.order(s2) is None and tokens(c, tok) - before == o2.amount + o2.fee


def test_no_verdict_while_pending_and_a_key_outside_the_panel_releases_nothing():
    c = OrderChain(pay_build=BUILD)
    claim = sources.get(TRIAL)
    p = W.plan(claim, units=10, price=4)
    panel = [Keypair() for _ in range(3)]
    keys = [bytes(k.pubkey()) for k in panel]
    buyer, tok = c.wallet(c.usdc, 100 * USDC)
    assert c.send([W.fund_panel_ix(p, K.stage1, buyer.pubkey(), tok, c.usdc, 2, keys)], buyer), c.err
    order = W.panel_address(p, K.stage1, buyer.pubkey())
    o = c.order(order)
    pending = W.check(claim, p[K.stage3][K.oracle])          # referee_pass with no verdict file: pending
    with pytest.raises(IdeaError):
        W.sign_stage(panel[0], order, o, pending, [(ORC, 10_000, Keypair().pubkey())])
    met = W.check(claim, p[K.stage1][K.oracle])
    payees = [(ORC, 10_000, Keypair().pubkey())]
    stranger = Keypair()
    for _ in range(2):
        sig = W.sign_stage(stranger, order, o, met, payees)
        assert not c.send(W.stage_verdict_ixs(c.payer.pubkey(), order, o, 2, keys, met, payees, [sig]), mark=False)
    assert c.order(order).paid == 0
    with pytest.raises(IdeaError):
        W.fund_panel_ix(p, K.pool, buyer.pubkey(), tok, c.usdc, 2, keys)
