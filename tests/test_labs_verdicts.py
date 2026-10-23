"""The two verdicts: the lab is paid when protocol + QC pass even if the science fails; the researcher is not."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from solders.keypair import Keypair

from knos import labs
from knos.labs import escrow, verdicts

FX = json.loads((Path(labs.__file__).parent / "fixtures" / "adaptyv.json").read_text(encoding="utf-8"))
SPEC = labs.Spec("proteins", FX["spec"], qc={"protocol_keys": ["experiment_type", "method", "target_id"], "runs": 3,
                                              "checks": [{"metric": "positive_control_kd_nm", "op": "<=", "value": 50, "over": "qc"}]},
                 claim={"metric": "kd_nm", "op": "<=", "value": 100, "agg": "min"})


def results() -> labs.Results:
    a = labs.get("adaptyv")
    return a.results(a.order(SPEC, "E"))


def plan() -> escrow.Plan:
    return escrow.plan("order-1", "proteins", 1_060_000_000, 100_000_000)


def test_lab_paid_when_protocol_and_qc_pass_and_the_science_fails():
    r = results()
    lab = verdicts.lab_verdict(SPEC, r)
    out = verdicts.outcome_verdict(SPEC, r, lab)
    assert lab.verdict == "PASS" and out.verdict == "FAIL"
    moves = escrow.settlement(plan(), lab, out)
    assert {(m["pot"], m["to"]) for m in moves} == {("lab", "lab"), ("lab", "treasury"), ("outcome", "funder")}
    assert not any(m["to"] == "researcher" for m in moves)
    p = plan()
    assert sum(m["amount"] for m in moves if m["to"] == "lab") == p.price
    assert sum(m["amount"] for m in moves if m["to"] == "treasury") == p.fee == p.price * 300 // 10_000   # 3% (config/fees.yaml)


def test_researcher_paid_when_the_claim_holds():
    spec = labs.Spec(SPEC.field, SPEC.protocol, SPEC.qc, {"metric": "kd_nm", "op": "<=", "value": 100, "agg": "min", "include_failed": True})
    r = results()
    # the claim holds only on runs that count: make one design bind (a different, passing result)
    r.runs[1]["measurements"].update({"binding": True, "kd_nm": 40.0})
    lab = verdicts.lab_verdict(spec, r)
    out = verdicts.outcome_verdict(spec, r, lab)
    assert (lab.verdict, out.verdict) == ("PASS", "PASS")
    assert ("outcome", "researcher") in {(m["pot"], m["to"]) for m in escrow.settlement(plan(), lab, out)}


def test_controls_never_count_as_the_researchers_result():
    r = results()
    assert r.runs[0]["control"] and r.runs[0]["measurements"]["kd_nm"] < 100      # the control binds well...
    assert verdicts.outcome_verdict(SPEC, r, verdicts.lab_verdict(SPEC, r)).verdict == "FAIL"   # ...and is not the design


@pytest.mark.parametrize("break_it, why", [
    (lambda r: r.qc.update(passed=False, why="positive control did not bind"), "QC did not pass"),
    (lambda r: r.protocol_executed.update(method="spr"), "protocol: method"),
    (lambda r: r.runs.pop(), "3 runs were ordered and 2 reported"),
    (lambda r: r.files.clear(), "no raw file"),
    (lambda r: r.runs[1].update(ok=False, why=None), "did not say why"),
    (lambda r: r.qc.update(positive_control_kd_nm=80.0), "QC check failed"),
])
def test_a_lab_that_did_not_do_the_work_right_is_not_paid_and_the_outcome_is_void(break_it, why):
    r = results()
    break_it(r)
    lab = verdicts.lab_verdict(SPEC, r)
    assert lab.verdict == "FAIL" and any(why in x for x in lab.reasons), lab.reasons
    out = verdicts.outcome_verdict(SPEC, r, lab)
    assert out.verdict == "VOID"
    moves = escrow.settlement(plan(), lab, out)
    assert {(m["to"]) for m in moves} == {"funder"} and sum(m["amount"] for m in moves) == plan().lab_pot + plan().reward


def test_settlement_refuses_mixed_up_verdicts():
    r = results()
    lab = verdicts.lab_verdict(SPEC, r)
    other = copy.deepcopy(r)
    other.runs[1]["measurements"]["kd_nm"] = 1.0
    with pytest.raises(verdicts.VerdictError, match="other evidence"):
        verdicts.outcome_verdict(SPEC, other, lab)
    fake = verdicts.Verdict("outcome", "PASS", [], lab.evidence_hash, lab.spec_hash)
    bad_lab = verdicts.Verdict("lab", "FAIL", [], lab.evidence_hash, lab.spec_hash)
    with pytest.raises(escrow.EscrowError, match="needs a LAB PASS"):
        escrow.settlement(plan(), bad_lab, fake)


# ---- m-of-n signed verdicts ------------------------------------------------------------------------------------------

REFS = [Keypair() for _ in range(3)]
SET = [str(k.pubkey()) for k in REFS]


def signed(**kw):
    r = results()
    v = verdicts.lab_verdict(SPEC, r)
    msg = verdicts.message("order-1", v, amount=kw.get("amount", 1_060_000_000), recipient=kw.get("recipient", "LabAddr"), mint="Mint",
                           expiry=kw.get("expiry", 2_000_000_000), nonce=kw.get("nonce", "n1"))
    return msg, verdicts.sign(msg, kw.get("signers", REFS[:2]))


def test_two_of_three_referees_release():
    msg, sigs = signed()
    assert verdicts.check(msg, sigs, SET, 2, now=1_900_000_000, amount=1_060_000_000, recipient="LabAddr") == []
    assert len(verdicts.digest(msg)) == 64


def test_m_minus_one_wrong_key_replay_expiry_and_changed_fields_are_refused():
    msg, sigs = signed(signers=REFS[:1])
    assert any("1 valid distinct" in p for p in verdicts.check(msg, sigs, SET, 2, now=0))
    msg, sigs = signed(signers=[REFS[0], Keypair()])
    assert any("not a registered referee" in p for p in verdicts.check(msg, sigs, SET, 2, now=0))
    msg, sigs = signed()
    assert any("same" in p or "1 valid" in p for p in verdicts.check(msg, sigs[:1] + sigs[:1], SET, 2, now=0))   # one key twice
    assert any("already used" in p for p in verdicts.check(msg, sigs, SET, 2, now=0, seen_nonces={"n1"}))
    assert any("expired" in p for p in verdicts.check(msg, sigs, SET, 2, now=2_000_000_001))
    assert any("the held money is" in p for p in verdicts.check(msg, sigs, SET, 2, now=0, amount=1))
    assert any("another recipient" in p for p in verdicts.check(msg, sigs, SET, 2, now=0, recipient="Thief"))
    tampered = dict(msg, verdict="PASS" if msg["verdict"] == "FAIL" else "FAIL")
    assert any("does not verify" in p for p in verdicts.check(tampered, sigs, SET, 2, now=0))
