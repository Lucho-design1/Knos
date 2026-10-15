"""The Adaptyv adapter (proteins), against recorded fixtures only: it never calls the live API in CI."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from knos import labs
from knos.labs import adaptyv, base, x402pay

FX = json.loads((Path(labs.__file__).parent / "fixtures" / "adaptyv.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to reach the network")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.delenv("ADAPTYV_API_KEY", raising=False)
    monkeypatch.delenv(base.LIVE_ORDERS, raising=False)


def spec(**kw) -> labs.Spec:
    return labs.Spec("proteins", dict(FX["spec"], **kw), qc={"protocol_keys": ["experiment_type", "method", "target_id"], "runs": 3},
                     claim={"metric": "kd_nm", "op": "<=", "value": 100, "agg": "min"}, title="fixture")


def test_the_fixture_is_labelled_as_a_mock_and_cites_the_docs():
    assert FX["label"].startswith("MOCK (synthetic, not a real API response)")
    assert "openapi.json" in FX["label"] and FX["source"].startswith("https://docs.adaptyvbio.com")
    assert all(k.split(" ", 1)[1].startswith("/api/v1/") for k in FX["responses"])


def test_quote_order_status_results_on_fixtures():
    a = labs.get("adaptyv")
    assert a.is_fixture and a.LIVE_READY and a.KEY_ENV == "ADAPTYV_API_KEY"
    q = a.quote(spec())
    assert (q.amount_usd, q.currency, q.turnaround_days, q.fixture) == ("1060.00", "USD", 28, True)
    o = a.order(spec(), "EscrowRef111")
    assert o.order_id and o.escrow_ref == "EscrowRef111" and o.spec_hash == spec().hash()
    assert a.lab_quote(o)["ready"] is True
    conf = a.confirm(o)
    assert conf["payment"]["kind"] == "machine" and conf["payment"]["pay_url"].endswith("/pay")
    assert a.status(o).state == base.COMPLETED and a.status(o).lab_state == "done"
    r = a.results(o)
    assert [x["id"] for x in r.runs] == ["pos_ctrl", "knos_design_1", "knos_design_2"]
    assert [x["control"] for x in r.runs] == [True, False, False]
    assert r.runs[0]["measurements"]["kd_nm"] == pytest.approx(2.1)
    assert r.runs[1]["measurements"]["binding"] is False          # a design that did not bind is a result, not a lab failure
    assert r.qc["passed"] and r.files and all(len(f["sha256"]) == 64 for f in r.files)
    calls = [c[:2] for c in a.fixtures.calls]
    assert ("POST", "/api/v1/experiments/cost-estimate") in calls and ("GET", f"/api/v1/experiments/{o.order_id}/results") in calls
    body = next(c[2] for c in a.fixtures.calls if c[:2] == ("POST", "/api/v1/experiments"))
    assert body["payment"] == {"method": "x402-exact"} and body["skip_draft"] is True


def test_the_invoice_402_is_paid_over_x402_on_base_sepolia():
    a = labs.get("adaptyv")
    o = a.order(spec(), "E")
    inv = a.confirm(o)["invoice_id"]
    status, body, headers = a.challenge(inv)
    assert status == 402
    ch = x402pay.decode_challenge(headers, body)
    req = x402pay.choose(ch["accepts"])
    assert req["network"] == x402pay.BASE_SEPOLIA and req["asset"] == x402pay.USDC[x402pay.BASE_SEPOLIA]
    import hashlib
    pay = x402pay.evm_payload(req, hashlib.sha256(b"knos test key").digest(), resource=ch["resource"])
    assert x402pay.check_evm(pay, req) == []
    assert json.loads(__import__("base64").b64decode(x402pay.encode(pay)))["accepted"] == req


def test_spec_rules_from_the_docs_are_checked_before_sending():
    a = labs.get("adaptyv")
    with pytest.raises(labs.LabError, match="bli or spr"):
        a.quote(spec(method="elisa"))
    with pytest.raises(labs.LabError, match="n_replicates"):
        a.quote(spec(n_replicates=9))
    with pytest.raises(labs.LabError, match="takes no method"):
        a.quote(labs.Spec("proteins", {"experiment_type": "thermostability", "method": "bli", "sequences": {"a": "MK"}}))
    assert a.fixtures.calls == []


def test_states_map_both_spellings():
    assert adaptyv.norm_state("waiting_for_materials") == adaptyv.norm_state("WaitingForMaterials") == base.SUBMITTED
    assert adaptyv.norm_state("Done") == base.COMPLETED and adaptyv.norm_state("canceled") == base.CANCELLED


def test_live_mode_needs_your_own_key_never_prints_it_and_never_orders_by_accident(monkeypatch):
    with pytest.raises(labs.NoKey, match=r"\$ADAPTYV_API_KEY"):
        labs.get("adaptyv", "live").quote(spec())
    seen = []

    def transport(method, url, body, headers):
        seen.append((method, url, headers))
        return 201, {"experiment_id": "x"}, {}
    monkeypatch.setenv("ADAPTYV_API_KEY", "secret-token-value")
    a = labs.get("adaptyv", "live", transport=transport)
    assert "secret-token-value" not in repr(a) and "secret-token-value" not in json.dumps(a.describe())
    with pytest.raises(labs.LabError, match=base.LIVE_ORDERS):
        a.order(spec(), "E")
    assert seen == []
    monkeypatch.setenv(base.LIVE_ORDERS, "1")
    a.order(spec(), "E")
    assert seen[0][1] == "https://devs.adaptyvbio.com/api/v1/experiments"
    assert seen[0][2]["Authorization"] == "Bearer secret-token-value"
