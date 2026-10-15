"""Private by default: no buyer data, no results and no lab failure rate appear in public Knos Record output."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from knos import labs
from knos.labs import privacy, verdicts

FX = json.loads((Path(labs.__file__).parent / "fixtures" / "adaptyv.json").read_text(encoding="utf-8"))
SPEC = labs.Spec("proteins", FX["spec"], qc={"runs": 3}, claim={"metric": "kd_nm", "op": "<=", "value": 100, "agg": "min"})


def one(salt: str, **kw):
    a = labs.get("adaptyv")
    o = a.order(SPEC, "E")
    r = a.results(o)
    lv = verdicts.lab_verdict(SPEC, r)
    ov = verdicts.outcome_verdict(SPEC, r, lv)
    pub = privacy.public_record(order_id=o.order_id, field="proteins", lab="adaptyv", salt=salt, spec_hash=SPEC.hash(), lab_v=lv,
                                outcome_v=ov, ordered_at="2026-10-14T20:00:00Z", results_at="2026-10-14T21:00:00Z",
                                turnaround_s=3600, releases=[{"to": "lab", "signature": "5" * 88}], **kw)
    return pub, r, o


def test_the_public_record_holds_hashes_timing_and_the_two_verdicts_only():
    pub, r, o = one(privacy.new_salt())
    assert set(pub) == {"lab_order", "field", "lab_ref", "lab_named", "spec_hash", "evidence_hash", "lab_verdict", "outcome_verdict",
                        "ordered_at", "results_at", "turnaround_s", "releases", "private"}
    assert pub["private"] is True and pub["lab_verdict"] == "PASS" and pub["outcome_verdict"] == "FAIL"
    private = {"runs": r.runs, "qc": r.qc, "sequences": FX["spec"]["sequences"], "order": o.order_id, "lab": "adaptyv",
               "target": FX["spec"]["target_id"], "price": "1060.00", "buyer": "buyer-org-name"}
    assert privacy.leaks(pub, private) == []


def test_a_labs_failure_rate_cannot_be_counted_without_its_consent():
    a, _, _ = one(privacy.new_salt())
    b, _, _ = one(privacy.new_salt())
    assert a["lab_ref"] != b["lab_ref"] and "adaptyv" not in json.dumps(a) and a["lab_named"] is False
    named, _, _ = one("s", lab_consents=True)
    assert named["lab_ref"] == "adaptyv" and named["lab_named"] is True


def test_publishing_is_the_buyers_opt_in():
    pub, _, _ = one("s", publish={"summary": "no design bound the target"})
    assert pub["private"] is False and pub["published"]["summary"].startswith("no design")


def test_a_payload_that_would_leak_a_secret_is_refused():
    with pytest.raises(ValueError, match="may not go public"):
        one("s", publish={"contact": "someone@example.com"})


def test_the_record_line_is_appended_through_knos_record(tmp_path):
    pub, _, _ = one("s", synthetic=True)
    got = privacy.record(pub, root=tmp_path)
    assert got is not None and got["kind"] == "verdict" and got["payload"]["synthetic"] is True
    line = (tmp_path / "journal.jsonl").read_text(encoding="utf-8")
    assert "adaptyv" not in line and "knos_design_1" not in line
