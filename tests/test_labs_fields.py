"""Every field through the same interface, on fixtures: chemistry (b12), materials (Materials Project), electronics
(PCBWay + a bench test), mechanical (Xometry stub), manual labs; and the devnet demo's case for each field."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from knos import labs
from knos.labs import base, escrow, verdicts

FX = Path(labs.__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    for k in ("MP_API_KEY", "B12_API_KEY", "PCBWAY_API_KEY", "KNOS_LABS_LIVE_ORDERS"):
        monkeypatch.delenv(k, raising=False)


def test_every_fixture_says_what_it_is():
    for f in FX.glob("*.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        assert doc["label"].split(" ")[0] in ("MOCK", "FIXTURE", "DOCUMENTED"), f.name
        assert doc["source"].startswith("https://"), f.name


def test_the_catalogue_names_every_field_and_its_key():
    cat = {c["lab"]: c for c in labs.catalogue()}
    assert {c["field"] for c in cat.values()} >= {"proteins", "chemistry", "materials", "electronics", "mechanical", "robotics"}
    assert cat["adaptyv"]["key_env"] == "ADAPTYV_API_KEY" and cat["adaptyv"]["live_ready"]
    assert cat["materials_project"]["key_env"] == "MP_API_KEY" and cat["pcbway"]["key_env"] == "PCBWAY_API_KEY"
    assert not cat["xometry"]["live_ready"] and not cat["jlcpcb"]["live_ready"]


def test_materials_project_is_computed_ground_truth_and_needs_a_key_live():
    a = labs.get("materials_project")
    spec = labs.Spec("materials", {"material_ids": ["mp-149"]}, qc={"runs": 1, "files": True},
                     claim={"metric": "energy_above_hull", "op": "<=", "value": 0.025, "agg": "max"})
    assert a.quote(spec).amount_usd == "0.00"
    o = a.order(spec, "E")
    r = a.results(o)
    assert r.runs[0]["measurements"]["band_gap"] == pytest.approx(0.853) and r.qc["passed"]
    lab = verdicts.lab_verdict(spec, r)
    assert lab.passed and verdicts.outcome_verdict(spec, r, lab).passed
    gap = labs.Spec("materials", {"material_ids": ["mp-149"]}, qc={"runs": 1}, claim={"metric": "band_gap", "op": ">=", "value": 2.0})
    assert verdicts.outcome_verdict(gap, r, verdicts.lab_verdict(gap, r)).verdict == "FAIL"     # a claim the DFT data refutes
    with pytest.raises(labs.NoKey, match="MP_API_KEY"):
        labs.get("materials_project", "live").results(o)


def test_b12_selenium_on_its_documented_examples():
    doc = json.loads((FX / "b12_selenium.json").read_text(encoding="utf-8"))
    a = labs.get("b12_selenium")
    spec = labs.Spec("chemistry", doc["spec"], qc={"runs": 1}, claim={"metric": "all_likely_feasible", "op": "==", "value": True, "agg": "all"})
    q = a.quote(spec)
    assert q.currency == "credits" and q.lines[0]["credits"] == 100
    o = a.order(spec, "E")
    key = next(c for c in a.fixtures.calls if c[:2] == ("POST", "/v1/route-searches"))
    assert o.order_id == "route-search-job-id"
    r = a.results(o)
    assert r.state == base.COMPLETED and r.runs[0]["ok"] and r.runs[0]["measurements"]["commercially_solved"] is True
    lab = verdicts.lab_verdict(spec, r)
    assert lab.passed and verdicts.outcome_verdict(spec, r, lab).passed
    with pytest.raises(labs.LabError, match="unknown fields"):
        a.quote(labs.Spec("chemistry", {"smiles": "CCO", "price": 1}))
    with pytest.raises(labs.LabError, match="KNOS_B12_SELENIUM_BASE"):
        labs.get("b12_selenium", "live")
    assert key


def test_b12_idempotency_key_is_stable_per_order(monkeypatch):
    seen = []
    monkeypatch.setenv("B12_API_KEY", "k")
    monkeypatch.setenv("KNOS_LABS_LIVE_ORDERS", "1")
    a = labs.get("b12_selenium", "live", base="https://b12.example", transport=lambda m, u, b, h: (seen.append(h), (202, {"id": "j", "status": "queued"}, {}))[1])
    spec = labs.Spec("chemistry", {"smiles": "CCO"})
    a.order(spec, "E1")
    a.order(spec, "E1")
    a.order(spec, "E2")
    keys = [h["Idempotency-Key"] for h in seen]
    assert keys[0] == keys[1] != keys[2] and seen[0]["Authorization"] == "Bearer k"


def electronics():
    doc = json.loads((FX / "pcbway.json").read_text(encoding="utf-8"))
    return doc, labs.Spec("electronics", doc["spec"], **{f: doc[f] for f in base.SPEC_FIELDS[2:4]})


def test_pcbway_fabrication_passes_the_lab_and_the_bench_test_fails_the_claim():
    doc, spec = electronics()
    a = labs.get("pcbway")
    q = a.quote(spec)
    assert q.amount_usd == "55.00" and q.turnaround_days == 5          # standard price + shipping
    o = a.order(spec, "EscrowRef")
    assert next(c[2] for c in a.fixtures.calls if c[1] == "/api/Pcb/PlaceOrder")["PONumber"] == "EscrowRef"
    assert a.status(o).state == base.COMPLETED
    r = a.with_bench(a.results(o), doc["bench"])
    lab = verdicts.lab_verdict(spec, r)
    out = verdicts.outcome_verdict(spec, r, lab)
    assert lab.verdict == "PASS" and out.verdict == "FAIL"
    moves = escrow.settlement(escrow.plan("o", "electronics", 55_000_000, 20_000_000), lab, out)
    assert ("lab", "lab") in {(m["pot"], m["to"]) for m in moves} and not any(m["to"] == "researcher" for m in moves)


def test_pcbway_refuses_what_its_docs_refuse():
    _doc, spec = electronics()
    a = labs.get("pcbway")
    with pytest.raises(labs.LabError, match="Layers"):
        a.quote(labs.Spec("electronics", dict(spec.protocol, Layers=3)))
    with pytest.raises(labs.LabError, match="Gerber"):
        a.order(labs.Spec("electronics", {k: v for k, v in spec.protocol.items() if k != "PcbFileUrl"}), "E")


def test_a_board_built_to_other_parameters_fails_the_lab_verdict():
    doc, spec = electronics()
    a = labs.get("pcbway")
    r = a.with_bench(a.results(a.order(spec, "E")), doc["bench"])
    r.protocol_executed["Layers"] = 4
    assert verdicts.lab_verdict(spec, r).verdict == "FAIL"


def test_stubs_say_what_is_missing():
    with pytest.raises(labs.LabError, match="partners, not buyers"):
        labs.get("xometry").quote(None)
    with pytest.raises(labs.LabError, match="application"):
        labs.get("jlcpcb").quote(None)


def test_a_manual_lab_binds_the_files_the_buyer_brings_back(tmp_path):
    lab = labs.get("b12_foundry")
    spec = labs.Spec("chemistry", {"quoted_usd": "4200.00", "target": "compound-7"}, qc={"runs": 1},
                     claim={"metric": "yield_pct", "op": ">=", "value": 30})
    assert lab.quote(spec).amount_usd == "4200.00"
    o = lab.order(spec, "EscrowRef")
    assert "founders@b12-labs.com" in o.raw["request"] and "EscrowRef" in o.raw["request"]
    f = tmp_path / "lcms.csv"
    f.write_text("t,signal\n0,1\n", encoding="utf-8")
    r = lab.deliver(o, [f], [{"id": "run-1", "ok": True, "measurements": {"yield_pct": 12.0}}], {"passed": True}, {"quoted_usd": "4200.00"})
    lab_v = verdicts.lab_verdict(spec, r)
    assert lab_v.passed and verdicts.outcome_verdict(spec, r, lab_v).verdict == "FAIL"
    f.write_text("t,signal\n0,2\n", encoding="utf-8")                  # a changed file is other evidence
    assert lab.deliver(o, [f], r.runs, r.qc, r.protocol_executed).evidence_hash() != r.evidence_hash()


@pytest.mark.parametrize("field", ["proteins", "electronics"])
def test_the_devnet_demo_cases_give_lab_pass_and_outcome_fail(field):
    from knos.labs import devnet
    case = devnet.field_case(field)
    a = labs.get(case["lab"])
    r = a.results(a.order(case["spec"], "E"))
    if case.get("bench"):
        r = a.with_bench(r, case["bench"])
    lab = verdicts.lab_verdict(case["spec"], r)
    assert (lab.verdict, verdicts.outcome_verdict(case["spec"], r, lab).verdict) == ("PASS", "FAIL")


def test_the_published_devnet_run_shows_the_lab_paid_and_the_researcher_not():
    got = json.loads((Path(__file__).resolve().parents[1] / "web" / "labs_devnet.json").read_text(encoding="utf-8"))
    assert got["synthetic"] is True and got["cluster"] == "devnet" and "TEST money" in got["what"]
    fields = {r["field"]: r for r in got["runs"]}
    assert {"proteins", "electronics"} <= set(fields)
    for r in fields.values():
        assert r["lab_verdict"]["verdict"] == "PASS" and r["outcome_verdict"]["verdict"] == "FAIL"
        assert r["balances_after"]["researcher"] == 0 and r["balances_after"]["lab"] >= r["plan"]["price"]
        assert r["public_record"]["private"] is True and r["lab_adapter"] not in json.dumps(r["public_record"])
        assert all(len(s["signature"]) >= 80 for s in r["lab_verdict"]["signatures"])
    assert fields["electronics"]["x402_solana"]["settlement"]["success"] is True
    assert fields["proteins"]["x402_base_sepolia"]["local_check"] == "ok"


# ---- robotics: simulation as the sealed test, independent re-runs ------------------------------------------------------

EX = Path(__file__).resolve().parents[1] / "examples" / "labs" / "robotics"


def test_the_sealed_test_scores_volumes_without_pylabrobot():
    from knos.labs import plr_runner
    got = plr_runner.score({"A1": 100.0, "A2": 149.0}, {"A1": 100.0, "A2": 150.0}, 0.5)
    assert got == {"max_abs_error_ul": 1.0, "wells_checked": 2, "wells_within_tolerance": 1}


def robot_spec(protocol: str) -> labs.Spec:
    return labs.Spec("robotics", {"protocol_file": str(EX / protocol), "sealed_test": str(EX / "sealed_test.json"), "reruns": 2},
                     qc={"runs": 2}, claim={"metric": "max_abs_error_ul", "op": "<=", "value": 0.5, "agg": "max"})


@pytest.mark.parametrize("protocol, outcome", [("serial_dilution.py", "PASS"), ("serial_dilution_wrong.py", "FAIL")])
def test_pylabrobot_reruns_judge_a_protocol_before_a_robot_lab_is_paid(protocol, outcome):
    """On the RECORDED runs of PyLabRobot 0.2.2 (fixtures/pylabrobot.json); scripts/labs_pylabrobot_check.py re-runs
    them on a real install."""
    from knos.labs import robotics
    a = labs.get("pylabrobot")
    assert a.is_fixture and a.label.startswith("FIXTURE")
    spec = robot_spec(protocol)
    assert a.quote(spec).amount_usd == "0.00"
    o = a.order(spec, "E")
    r = a.results(o, spec)
    assert r.qc["reruns_agree"] and r.protocol_executed["pylabrobot"] == robotics.PIN
    lab = verdicts.lab_verdict(spec, r)
    assert lab.verdict == "PASS" and verdicts.outcome_verdict(spec, r, lab).verdict == outcome


def test_live_mode_without_pylabrobot_says_so_in_words(monkeypatch):
    from knos.labs import robotics
    monkeypatch.setattr(robotics, "python", lambda: None)
    a = labs.get("pylabrobot", "live")
    spec = robot_spec("serial_dilution.py")
    with pytest.raises(labs.LabError, match="PyLabRobot is not installed"):
        a.results(a.order(spec, "E"), spec)


def test_a_protocol_nobody_recorded_is_refused_not_invented(tmp_path):
    p = tmp_path / "other.py"
    p.write_text("async def protocol(lh, plate, tips):\n    pass\n", encoding="utf-8")
    spec = labs.Spec("robotics", {"protocol_file": str(p), "sealed_test": str(EX / "sealed_test.json")}, qc={"runs": 2})
    a = labs.get("pylabrobot")
    with pytest.raises(labs.LabError, match="no recorded PyLabRobot run"):
        a.results(a.order(spec, "E"), spec)
