"""A measurement end to end on SYNTHETIC tickets: the honest window pays the tiers its lift reaches, every cheat check
refuses its known-bad case, and every measurement writes Knos Record entries that parse and hold no secret."""
from __future__ import annotations

import copy
import json
import re
import sys
import types

import pytest

from knos.outcomes import escrow, measure, recordio, synth, tamper
from knos.outcomes.spec import spec_hash, utc
from knos.settle.v2 import pay

N, BEFORE, SEED = 10_000, 300, 7


@pytest.fixture(scope="module")
def world():
    s = synth.example_spec()
    s["bootstrap"]["resamples"] = 200
    rows = synth.tickets(s, N, seed=SEED, before=BEFORE)
    history = [r for r in rows if utc(r["created_at"]) < utc(s["window"]["start"])]
    lock = measure.lock_for(s, history, escrow.orders(s))
    return s, rows, lock


def run(s, lock, rows, *, now=None, code=None):
    return measure.run(s, lock, rows, data_name="d" * 40, data_sha256="e" * 64, now=now if now is not None else utc(s["window"]["end"]) + 60, code=code)


def test_the_honest_window_pays_the_two_tiers_its_lift_reaches_and_not_the_third(world):
    s, rows, lock = world
    r = run(s, lock, rows)
    assert not r["refused"] and r["passed"] and r["findings"] == []
    assert [t["passed"] for t in r["tiers"]] == [True, True, False]
    assert r["synthetic"] is True and r["data"]["in_window"] == N
    assert 0.10 <= r["lower_bound"] < r["lift"] < 0.20
    assert r["bootstrap"]["seed"] == s["bootstrap"]["seed"]
    # the result names itself
    body = {k: v for k, v in r.items() if k != "result_hash"}
    from knos.outcomes.spec import canonical
    import hashlib
    assert r["result_hash"] == hashlib.sha256(canonical(body)).hexdigest()


def test_each_passed_tier_carries_exactly_the_audience_knos_pay_reads(world):
    s, rows, lock = world
    r = run(s, lock, rows)
    for k, t in enumerate(r["tiers"]):
        order = escrow.order_address(s, k)
        assert t["order"] == str(order)
        if t["passed"]:
            want = pay.order_pay_audience(order, "d" * 40, escrow.terms_hash(s, k), pay.MERGE, s["escrow"]["issue"],
                                          [(s["parties"]["seller"]["id"], 10_000, pay.Pubkey.from_string(s["parties"]["seller"]["address"]))])
            assert t["audience"] == want
            assert pay.payees_of(t["audience"]) == [(142920951, 10_000, pay.Pubkey.from_string(s["parties"]["seller"]["address"]))]
        else:
            assert "audience" not in t


def test_a_measurement_before_the_window_closes_is_refused(world):
    s, rows, lock = world
    r = run(s, lock, rows, now=utc(s["window"]["end"]) - 1)
    assert r["refused"] and not r["passed"] and not any(t["passed"] for t in r["tiers"])
    assert "window closes" in r["why"][0]


def _edited(s, f):
    t = copy.deepcopy(s)
    f(t)
    return t


@pytest.mark.parametrize("name,edit,category", [
    ("a tier's bar lowered after funding", lambda t: t["tiers"][2].__setitem__("min_lift", 0.15), "spec_hash_changed"),
    ("the window moved", lambda t: t["window"].__setitem__("end", "2026-09-30T00:00:00Z"), "window_changed"),
    ("the salt changed", lambda t: t["control"].__setitem__("salt", "ab" * 16), "salt_changed"),
    ("the control share shrunk", lambda t: t["control"].__setitem__("share", 0.1), "control_drift"),
])
def test_a_spec_changed_after_funding_is_refused(world, name, edit, category):
    s, rows, lock = world
    r = run(_edited(s, edit), lock, rows)
    assert r["refused"] and not any(t["passed"] for t in r["tiers"]), name
    assert category in {f["category"] for f in r["findings"]}, (name, r["findings"])


def test_measuring_code_other_than_the_locked_code_is_refused(world):
    s, rows, lock = world
    r = run(s, lock, rows, code="0" * 64)
    assert r["refused"] and {f["category"] for f in r["findings"]} >= {"measurement_code_drift"}
    assert lock["measurement_commit"] == tamper.code_hash()


def test_history_rewritten_after_funding_is_data_tampering(world):
    s, rows, lock = world
    old = next(i for i, r in enumerate(rows) if utc(r["created_at"]) < utc(s["window"]["start"]))
    edited = [dict(r) for r in rows]
    edited[old]["status"] = "open" if edited[old]["status"] == "solved" else "solved"
    r = run(s, lock, edited)
    assert r["refused"] and "data_tampering" in {f["category"] for f in r["findings"]}


def test_an_item_written_twice_is_data_tampering(world):
    s, rows, lock = world
    r = run(s, lock, rows + [rows[-1]])
    assert r["refused"] and any(f["rule"] == "outcome.duplicates" for f in r["findings"])


def test_deleting_the_agents_failures_drifts_the_control_share_and_is_refused(world):
    s, rows, lock = world
    cheat = synth.drop_treated_failures(rows)
    r = run(s, lock, cheat)
    assert r["refused"] and any(f["rule"] == "outcome.drift" for f in r["findings"])
    assert r["lift"] > run(s, lock, rows)["lift"]           # the cheat would have raised the lift


def test_moving_resolved_control_tickets_to_the_agent_is_refused(world):
    s, rows, lock = world
    r = run(s, lock, synth.relabel(rows, 50))
    assert r["refused"] and any(f["rule"] == "outcome.arm" and "50 item" in f["detail"] for f in r["findings"])


def test_too_few_items_is_refused_not_failed(world):
    s, rows, lock = world
    r = run(s, lock, rows[:BEFORE + 40])
    assert r["refused"] and any("at least 30" in w for w in r["why"])


def test_the_cheat_library_is_consulted_when_it_is_installed(world, monkeypatch):
    s, rows, lock = world
    seen = {}

    class F:
        rule, category, detail, path, severity = "lib.extra", "judge_drift", "from the library", "", "refuse"

    def scan_outcome(funded, now, *, control_tolerance=0.02):
        seen["args"] = (funded["spec_hash"], now["spec_hash"], control_tolerance)
        return [F()]
    fake = types.ModuleType("knos.cheats")
    fake.scan_outcome = scan_outcome
    monkeypatch.setitem(sys.modules, "knos.cheats", fake)
    import knos
    monkeypatch.setattr(knos, "cheats", fake, raising=False)
    r = run(s, lock, rows)
    assert seen["args"][0] == seen["args"][1] == spec_hash(s)
    assert r["refused"] and any(f["category"] == "judge_drift" for f in r["findings"])


# ---- Knos Record -----------------------------------------------------------------------------------------------------
SECRET = re.compile(r"eyJ[A-Za-z0-9_-]{10,}|-----BEGIN|ghp_|github_pat_|@[a-z0-9-]+\.[a-z]{2,}")


def test_every_measurement_writes_record_entries_that_parse_and_hold_no_secret(world, tmp_path, monkeypatch):
    s, rows, lock = world
    import knos
    monkeypatch.setitem(sys.modules, "knos.record", None)          # RECORD's package absent: the fallback file
    monkeypatch.delattr(knos, "record", raising=False)
    honest, cheat = run(s, lock, rows), run(s, lock, synth.relabel(rows, 50))
    recordio.measurement(honest, root=tmp_path)
    recordio.measurement(cheat, root=tmp_path)
    recordio.money("payout", spec_hash=honest["spec_hash"], tier="lift-5", amount=5_000_000, mint=s["escrow"]["mint"], tx="5" * 88, synthetic=True, root=tmp_path)
    lines = (tmp_path / recordio.FALLBACK).read_text(encoding="utf-8").splitlines()
    entries = [json.loads(ln) for ln in lines]
    assert [e["kind"] for e in entries] == ["verification", "verification", "cheat", "payout"]
    assert all(e["payload"]["synthetic"] is True and e["domain"] == "outcomes" for e in entries)
    assert entries[2]["payload"]["cheat"] == "control_drift"
    assert all(entries[i]["prev"] == entries[i - 1]["hash"] for i in range(1, len(entries)))
    assert not SECRET.search("\n".join(lines)) and "SYN-" not in "\n".join(lines)      # no item ids either


def test_entries_go_through_records_own_api_when_it_is_installed(world, tmp_path, monkeypatch):
    s, rows, lock = world
    calls = []
    fake = types.ModuleType("knos.record")
    fake.append = lambda kind, payload, *, claim=None, domain="", root=None: calls.append((kind, domain, claim)) or {"kind": kind}
    monkeypatch.setitem(sys.modules, "knos.record", fake)
    import knos
    monkeypatch.setattr(knos, "record", fake, raising=False)
    recordio.measurement(run(s, lock, rows), root=tmp_path)
    assert calls == [("verification", "outcomes", spec_hash(s))] and not (tmp_path / recordio.FALLBACK).exists()


@pytest.mark.parametrize("bad", [{"token": "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig"}, {"k": list(range(64))}, {"who": "a@b.com"},
                                 {"pem": "-----BEGIN PRIVATE KEY-----"}])
def test_a_payload_with_a_secret_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        recordio.append("verification", bad, root=tmp_path)


def test_deleting_900_of_the_agents_failures_is_caught_and_the_limit_is_what_the_doc_says(world):
    s, rows, lock = world
    r = run(s, lock, synth.drop_treated_failures(rows, 900))
    assert r["refused"] and any(f["rule"] == "outcome.drift" for f in r["findings"])
    small = run(s, lock, synth.drop_treated_failures(rows, 100))         # below four standard errors: not seen by the share
    assert not any(f["rule"] == "outcome.drift" for f in small["findings"])


def test_a_lock_that_names_no_measuring_code_is_refused(world):
    s, rows, lock = world
    r = run(s, {**lock, "measurement_commit": ""}, rows)
    assert r["refused"] and any(f["category"] == "measurement_code_drift" for f in r["findings"])
    assert lock["issue"] == s["escrow"]["issue"]


def test_the_data_token_goes_only_with_a_named_secret_and_never_through_a_redirect():
    from knos.outcomes import data
    seen = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"[]"

    def opener(req, timeout=0):
        seen.append(dict(req.header_items()))
        return Resp()
    data.http_read("https://help.example/t", None, env={"KNOS_OUTCOME_DATA_TOKEN": "x", "OTHER": "y"}, opener=opener)
    assert "Authorization" not in seen[-1]
    data.http_read("https://help.example/t", "SUPPORT_TOKEN", env={"SUPPORT_TOKEN": "t0k"}, opener=opener)
    assert seen[-1]["Authorization"] == "Bearer t0k"
    with pytest.raises(data.DataError):
        data.http_read("https://help.example/t", "SUPPORT_TOKEN", env={"KNOS_OUTCOME_DATA_TOKEN": "x"}, opener=opener)
    with pytest.raises(data.DataError):
        data._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example/")
