"""`knos idea commit | sign | release | refund | state` in the Solana runtime (LiteSVM, the knos_pay 0.3.34 test build;
the oracle reads come from the recorded fixture). The payee is chosen at commit and nothing else can be paid; the panel
never holds the funder's or payee's key; referee_pass / lab_qc need M SIGNED verdicts; a refund is never called a
release. Synthetic test units; referee keys made per test (an unlisted panel, labelled)."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("solders.litesvm")

from solders.keypair import Keypair  # noqa: E402

from _order import USDC, OrderChain  # noqa: E402
from _pay2 import ChainLedger  # noqa: E402

from knos import cli, ideas  # noqa: E402
from knos.ideas import IdeaError, K, sources, wanted as W  # noqa: E402
from knos.ideas import commit as C  # noqa: E402
from knos.ideas.cli import GROUP, PRICE, UNITS  # noqa: E402
from knos.settle.v2 import pay  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "ideas" / "recorded-fixture.json"
BUILD = "knos_pay_v2_0334_test.so"
PAPER = "arxiv:1606.00335"
RETRACTED = "doi:10.1016/s0140-6736(97)11096-0"
ORC = "0000-0002-1825-0097"          # ORCID's public test record stands in for the researcher
O_ = W.ORACLE
STAGES = [(O_.preprint_posted, 2000), (O_.referee_pass, 5000), (O_.lab_qc, 3000)]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for k in ideas.ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no live API call in tests")))
    monkeypatch.setenv(ideas.FIXTURES_ENV, str(FIXTURE))


def tokens(c: OrderChain, account) -> int:
    d = c.data(account)
    return int.from_bytes(d[64:72], "little") if d and len(d) >= 72 else 0


@pytest.fixture()
def world():
    c = OrderChain(pay_build=BUILD)
    led = ChainLedger(c)
    buyer, tok = c.wallet(c.usdc, 100 * USDC)
    panel = [Keypair() for _ in range(3)]
    wallet = Keypair().pubkey()
    payee = C.parse_payee(f"orcid:{ORC}@{wallet}")
    doc = C.commit(sources.get(PAPER), units=10, price=4, payee=payee, funder=buyer, funder_token=tok, mint=c.usdc, led=led,
                   stages=STAGES, panel=(2, [str(k.pubkey()) for k in panel]), unlisted_panel=True)
    return c, led, buyer, tok, panel, wallet, doc


def test_the_payee_is_required_and_parsed_and_the_panel_rules_hold():
    for bad in ("", "torvalds", "github:abc", "orcid:0000-0002-1825-0098", "github:7@notanaddress"):
        with pytest.raises(IdeaError):
            C.parse_payee(bad)
    w = str(Keypair().pubkey())
    assert C.parse_payee(w)[K.kind] == C.parse_payee(w)[K.kind] and C.parse_payee("github:7")[K.id] == 7
    keys = [str(Keypair().pubkey()) for _ in range(3)]
    funder = keys[0]
    with pytest.raises(IdeaError):
        C.parse_panel("2:" + ",".join(keys), funder=funder, unlisted_panel=True)            # the funder judges itself
    with pytest.raises(IdeaError):
        C.parse_panel("2:" + ",".join(keys), payee_wallet=keys[1], unlisted_panel=True)     # the payee judges itself
    with pytest.raises(IdeaError):
        C.parse_panel("2:" + ",".join(keys))                                               # off the registry, not allowed
    m, got, label = C.parse_panel("2:" + ",".join(keys), unlisted_panel=True)
    assert (m, got) == (2, keys) and label.startswith("UNLISTED PANEL")
    for bad in ("2:" + keys[0], "0:" + ",".join(keys), "2:" + ",".join([keys[0], keys[0]]), "x:" + keys[0]):
        with pytest.raises(IdeaError):
            C.parse_panel(bad, unlisted_panel=True)


def test_commit_refuses_a_retracted_paper_and_a_wallet_payee_on_the_github_route():
    c = OrderChain(pay_build=BUILD)
    led = ChainLedger(c)
    buyer, tok = c.wallet(c.usdc, 100 * USDC)
    wallet = C.parse_payee(str(Keypair().pubkey()))
    with pytest.raises(IdeaError):
        C.commit(sources.get(RETRACTED), units=10, price=4, payee=C.parse_payee("github:7"), funder=buyer, funder_token=tok, mint=c.usdc, led=led)
    with pytest.raises(IdeaError):
        C.commit(sources.get(PAPER), units=10, price=4, payee=wallet, funder=buyer, funder_token=tok, mint=c.usdc, led=led)
    assert W.plan(sources.get(PAPER), units=10, price=4)[K.payees] == []                  # no payee is ever assumed


def test_a_met_stage_is_released_to_the_committed_payee_and_nothing_else_is_paid(world, tmp_path):
    c, led, buyer, tok, panel, wallet, doc = world
    assert doc["judge"] == "panel" and doc["panel"]["label"].startswith("UNLISTED PANEL")
    recs = [C.sign(doc, K.stage1, r, led) for r in panel]
    assert {r["verdict"] for r in recs} == {W.PASS}
    # a stranger, a verdict naming another payee, a FAIL verdict and one verdict alone are all refused before sending
    with pytest.raises(IdeaError):
        C.sign(doc, K.stage1, Keypair(), led)
    swapped = dict(recs[1], payees=f"77.10000.{Keypair().pubkey()}")
    with pytest.raises(IdeaError):
        C.release(doc, K.stage1, [recs[0], swapped], buyer, led)
    with pytest.raises(IdeaError):
        C.release(doc, K.stage1, recs[:1], buyer, led)
    with pytest.raises(IdeaError):
        C.refund(doc, K.stage1, recs[:2], buyer, led)
    got = C.release(doc, K.stage1, recs[:2], buyer, led)
    assert got[K.status] == "released" and len(got["sent"]) == 2
    assert tokens(c, pay.ata(wallet, c.usdc)) == doc["orders"][K.stage1][K.amount]
    st = C.state(doc, led)
    assert st[K.stages][K.stage1][K.locked] == 0 and st[K.locked_total] == sum(doc["orders"][s][K.amount] for s in (K.stage2, K.stage3))


def test_review_stages_need_m_signed_verdicts_and_a_missed_stage_is_refunded_not_released(world, tmp_path):
    c, led, buyer, tok, panel, wallet, doc = world
    report = tmp_path / "review.txt"
    report.write_text("SYNTHETIC review report\n")
    # an unsigned verdict file is shown but never accepted: nothing can be signed or released on it
    unsigned = tmp_path / "unsigned.json"
    unsigned.write_text(json.dumps({K.claim: doc[K.claim][K.id], K.passed: True}))
    ev = W.check(doc[K.claim], O_.referee_pass, verdict=str(unsigned), panel=(2, doc["panel"]["keys"]))
    assert ev["accepted"] is False and W.verdict_of(ev) is None
    with pytest.raises(IdeaError):
        C.sign(doc, K.stage2, panel[0], led)                                    # a review stage needs the referee's result
    passes = [C.sign(doc, K.stage2, r, led, passed=True, review=report) for r in panel[:2]]
    signed = tmp_path / "signed.json"
    signed.write_text(json.dumps(passes))
    ok = W.check(doc[K.claim], O_.referee_pass, verdict=str(signed), panel=(2, doc["panel"]["keys"]))
    assert ok[K.met] is True and ok["accepted"] is True
    one = tmp_path / "one.json"
    one.write_text(json.dumps(passes[:1]))
    assert W.check(doc[K.claim], O_.referee_pass, verdict=str(one), panel=(2, doc["panel"]["keys"]))["accepted"] is False
    assert C.release(doc, K.stage2, passes, buyer, led)[K.status] == "released"
    # the lab stage failed QC: two FAIL verdicts refund it to the buyer now; it is called refunded
    before = tokens(c, tok)
    amount = doc["orders"][K.stage3][K.amount]
    fails = [C.sign(doc, K.stage3, r, led, passed=False, review=report) for r in (panel[2], panel[0])]
    with pytest.raises(IdeaError):
        C.release(doc, K.stage3, fails, buyer, led)
    got = C.refund(doc, K.stage3, fails, buyer, led)
    assert got[K.status] == "refunded" and tokens(c, tok) - before == amount + pay.order_fee(amount)
    assert tokens(c, pay.ata(wallet, c.usdc)) == doc["orders"][K.stage2][K.amount]          # the refund paid the payee nothing
    assert C.state(doc, led)[K.locked_total] == doc["orders"][K.stage1][K.amount]


def test_the_commitment_file_is_what_state_and_release_read(world, tmp_path):
    c, led, buyer, tok, panel, wallet, doc = world
    path = tmp_path / "idea.commit.json"
    path.write_text(json.dumps(doc))
    assert C.is_commitment(path) and C.load(path)[K.payee] == doc[K.payee]
    tampered = dict(doc, plan_args=dict(doc["plan_args"], price=5))
    path.write_text(json.dumps(tampered))
    with pytest.raises(IdeaError):
        C.load(path)


def test_defaults_warnings_and_fields(capsys):
    published = sources.get("pmid:42806035")
    assert [o for o, _ in W.default_stages(published)][0] == O_.not_retracted       # completable for a published paper
    assert [o for o, _ in W.default_stages(sources.get(PAPER))][0] == O_.preprint_posted
    bad = sources.get(RETRACTED)
    assert W.retraction_warning(bad) and W.plan(bad, units=10, price=4)["warnings"]
    d = W.demand(bad)
    assert d["lean"]["word"] == W.RETRACTED_WORD and d["warning"]
    # a superconductor paper OpenAlex files under a geophysics topic is a materials paper (SYNTHETIC fixture work)
    work = {"primary_topic": {"display_name": "High-pressure geophysics and materials", "field": {"display_name": ideas.FIELDS[9]}}}
    concepts = [{"display_name": "Materials science", "level": 0, "score": 0.57}, {"display_name": "Superconductivity", "level": 2, "score": 0.77}]
    assert sources.openalex_field(work, concepts)[0] == ideas.FIELDS[16]
    assert sources.openalex_field(work, [])[0] == ideas.FIELDS[9]                       # offline: the topic's field stands
    chem_only = [{"display_name": "Chemistry", "level": 0, "score": 0.59}, {"display_name": "Physics", "level": 0, "score": 0.12}]
    assert sources.openalex_field(work, chem_only)[0] == ideas.FIELDS[16]               # the topic names materials
    supported = [{"display_name": "Geology", "level": 0, "score": 0.6}]
    assert sources.openalex_field(work, supported)[0] == ideas.FIELDS[9]                # a concept supports the topic's field
    bio = {"primary_topic": {"display_name": "CRISPR and Genetic Engineering", "field": {"display_name": ideas.FIELDS[2]}}}
    assert sources.openalex_field(bio, [{"display_name": "Biology", "level": 0, "score": 0.84}])[0] == ideas.FIELDS[2]
    # the CLI refuses a commit with no payee (it is a required option) before anything is sent
    assert cli.main([GROUP, "commit", "x.json", UNITS, "10", PRICE, "4"]) != 0
