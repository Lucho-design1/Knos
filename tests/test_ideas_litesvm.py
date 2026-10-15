"""A pull commitment released IN STAGES in the Solana runtime (LiteSVM, the knos_pay test build; the GitHub token is
the harness's test issuer, labelled): the buyer locks N x P as one private order per stage; stage 1's milestone is
met and the judge's token pays it to the researcher; stage 2 misses its deadline and is refunded to the buyer with its
fee; stage 3 stays locked. knos.ideas.wanted.state reads exactly that back from the chain."""
from __future__ import annotations

import pytest

pytest.importorskip("solders.litesvm")

from solders.keypair import Keypair  # noqa: E402

from _order import USDC, OrderChain, user  # noqa: E402
from _pay2 import ChainLedger, WF_SHA  # noqa: E402

from knos import ideas  # noqa: E402
from knos.ideas import K, wanted as W  # noqa: E402
from knos.settle.v2 import pay  # noqa: E402

JUDGE_REPO = 27_182_818


def test_a_pull_commitment_is_paid_stage_by_stage_and_refunded_where_the_milestone_is_missed():
    c = OrderChain()
    maker = user()
    idea = ideas.person("A synthetic test claim: compound Z raises yield of reaction Q by 20 percent.", field_name="Chemistry")
    p = W.plan(idea, units=10, price=4, stages=[(W.ORACLE.preprint_posted, 2000), (W.ORACLE.referee_pass, 3000), (W.ORACLE.lab_qc, 5000)],
               repo_id=JUDGE_REPO, maker_github_id=maker, wf_sha=WF_SHA, stage_work_s=[30 * 86_400, 120, 90 * 86_400])
    buyer, tok = c.wallet(c.usdc, 100 * USDC)
    before = c.balance(tok)
    for part in p[K.stages]:
        assert c.send([W.fund_ix(p, part, buyer.pubkey(), tok, c.usdc)], buyer, tag="idea_stage_lock"), c.err
    assert before - c.balance(tok) == p["buyer_pays"]
    led = ChainLedger(c)
    s = W.state(led, p, str(c.usdc))
    assert [s[K.parts][k][K.locked] for k in p[K.stages]] == [8 * USDC, 12 * USDC, 20 * USDC] and s[K.locked_total] == 40 * USDC
    # stage 1: the milestone is met; the judge's signed token pays the researcher the stage's amount
    wallet = Keypair().pubkey()
    o1 = W.address(p, K.stage1, buyer.pubkey())
    assert c.pay(o1, [(maker, 10_000, wallet)], repository_id=JUDGE_REPO, tag="idea_stage_release"), c.err
    assert c.balance(pay.ata(wallet, c.usdc)) == 8 * USDC and c.data(o1) is None
    # stage 2: nobody met it within its 120 s; past the deadline the buyer gets the amount and the fee back
    o2 = W.address(p, K.stage2, buyer.pubkey())
    o = c.order(o2)
    c.warp(121 + pay.CLOCK_SLACK)
    mid = c.balance(tok)
    assert c.send([W.refund_ix(c.payer.pubkey(), o2, o)], tag="idea_stage_refund"), c.err
    assert c.balance(tok) - mid == o.amount + o.fee
    # stage 3 is still locked, and the state says so
    s = W.state(led, p, str(c.usdc))
    assert s[K.parts][K.stage1][K.locked] == 0 and s[K.parts][K.stage2][K.locked] == 0 and s[K.parts][K.stage3][K.locked] == 20 * USDC


def test_a_stage_is_paid_only_by_the_judge_repositorys_token():
    c = OrderChain()
    maker, thief = user(), user()
    idea = ideas.person("A synthetic test claim: a material keeps 90 percent conductivity after bending.", field_name="Materials Science")
    p = W.plan(idea, units=10, price=4, repo_id=JUDGE_REPO, maker_github_id=maker, wf_sha=WF_SHA)
    buyer, tok = c.wallet(c.usdc, 100 * USDC)
    assert c.send([W.fund_ix(p, K.stage1, buyer.pubkey(), tok, c.usdc)], buyer), c.err
    o1 = W.address(p, K.stage1, buyer.pubkey())
    # a signed run of ANOTHER repository's workflow (not the plan's judge) cannot release the stage
    assert not c.pay(o1, [(thief, 10_000, Keypair().pubkey())], repository_id=JUDGE_REPO + 1)
    assert c.order(o1) is not None
