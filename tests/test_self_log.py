"""knos self: every attempt, verdict, cheat caught and payout of the loop goes to Knos Record (one hash-chained file,
held in Sibyl tier by tier). A small in-memory store stands in for Sibyl's here; the loop uses Sibyl's own."""
from __future__ import annotations

from knos import record
from knos.self import publog


class Store:
    def __init__(self):
        self.warm, self.cold, self.ref = {}, [], {}

    def put(self, cat, key, value):
        self.warm[(cat, key)] = value

    def journal(self, **kw):
        self.cold.append(kw)

    def set_reference(self, key, value, kind=""):
        self.ref[key] = value


VERDICT = {"decision": "refused", "judge_hash": "a" * 64, "candidate_judge_hash": "b" * 64, "reasons": ["self.core_path: x"],
           "findings": [{"rule": "self.core_path", "category": "core_path", "path": "src/knos/referee/works.py", "detail": "", "severity": "refuse"},
                        {"rule": "x", "category": "test_edited", "path": "", "detail": "", "severity": "flag"}],
           "tiers": {}}
ACCEPT = {"decision": "accept", "judge_hash": "a" * 64, "candidate_judge_hash": "a" * 64, "reasons": [], "findings": [],
          "metric_parent": 97, "metric_candidate": 60, "gain": 37,
          "tiers": {"public": {"passed": True, "tests": {"total": 47, "passed": 47, "failed": 0, "errors": 0, "skipped": 0}},
                    "sealed": {"passed": True, "rerun_agrees": True, "bundle_sha256": "c" * 64, "metric_parent": {"metric": 97},
                               "metric_candidate": {"metric": 60}, "tests": {"total": 5, "passed": 5}},
                    "shadow": {"passed": True, "disagreements": []}}}


def test_a_refused_iteration_writes_its_cheat_refusal_and_verdict(tmp_path):
    log = publog.Log(tmp_path, store=Store())
    node = {"id": "v1", "parent": "v0", "target": "mcp-cold-start", "decision": "refused", "stage": "sealed", "diff_hash": "d" * 64,
            "commit": "e" * 40, "agent": "claude-code"}
    lines = publog.iteration(log, node=node, verdict=VERDICT, choice=None, lineage=["v1", "v0"], payout=None)
    assert [x["kind"] for x in lines] == ["experiment", "cheat", "refusal", "verdict", "claim"]
    assert all(x["domain"] == "self" and x["claim"] == "self:mcp-cold-start:v1" for x in lines)
    assert lines[1]["payload"]["cheat"] == "core_path"                          # flags are not cheats caught
    assert lines[3]["payload"]["judge_hash"] == "a" * 64 and lines[3]["payload"]["referee"] == "main"
    assert record.entries(tmp_path)[-1]["hash"] == lines[-1]["hash"]


def test_an_accepted_iteration_writes_its_tiers_and_payout_with_signatures(tmp_path):
    store = Store()
    log = publog.Log(tmp_path, store=store)
    node = {"id": "v2", "parent": "v0", "target": "mcp-cold-start", "decision": "canary", "stage": "canary", "diff_hash": "d" * 64,
            "commit": "e" * 40, "agent": "claude-code", "metric": 60}
    pay = {"amount": 1_000_000, "fee": 50_000, "mint": "4C6dtRowv5gGgdVxX3YdHmRwoD5vNt1W5wXGRcCvp3X1", "payee": "EK7H81j97oaupJijuzaK2WZvaLVKgJosbxyCiqWPupHs",
           "payout_tx": "5" * 88, "fee_tx": "4" * 88, "cluster": "devnet"}
    choice = {"parent": "v0", "seed": 1, "draws": [{"id": "v0", "alpha": 1, "beta": 1, "draw": 0.5, "mean": 0.5}]}
    lines = publog.iteration(log, node=node, verdict=ACCEPT, choice=choice, lineage=["v2", "v0"], payout=pay)
    kinds = [x["kind"] for x in lines]
    assert kinds == ["experiment", "verification", "verification", "verification", "verdict", "payout", "claim"]
    sealed = lines[2]["payload"]
    assert sealed["tier"] == "sealed" and sealed["metric"] == 60 and sealed["metric_parent"] == 97 and sealed["rerun_agrees"]
    assert set(sealed) <= {"tier", "passed", "counts", "rerun_agrees", "metric_parent", "metric", "bundle_sha256", "diff_hash", "judge_hash"}
    assert lines[5]["payload"]["payout_tx"] == "5" * 88 and lines[5]["payload"]["test_money"] is True
    assert store.warm[("record_claim", "self:mcp-cold-start:v2")]["lineage"] == ["v2", "v0"]
    assert len(store.cold) == len(lines)
    seqs = [e["seq"] for e in record.entries(tmp_path)]
    assert seqs == list(range(len(seqs)))


def test_the_committed_example_is_a_real_unbroken_record_of_the_runs():
    import json
    from pathlib import Path
    ex = Path(__file__).resolve().parents[1] / "examples" / "self"
    got = record.verify(ex, offline=True, use_sibyl=False,                 # the loop's own devnet anchoring key
                        signers=["3gQxtRxsuuicL7gkcoaGZwVtP8RverKwn1wGEpd3uYDM"])
    assert got["ok"] and got["problems"] == [] and got["anchored"] == got["lines"] - 1
    archive = json.loads((ex / "archive.json").read_text())
    decisions = {n["id"]: n["decision"] for n in archive["nodes"]}
    assert decisions == {"v0": "root", "v1": "canary", "v2": "refused", "v3": "canary", "v4": "refused", "v5": "held"}
    judged = {e["payload"]["judge_hash"] for e in record.entries(ex) if e["kind"] == "verdict" and e["payload"].get("judge_hash")}
    assert judged == {archive["nodes"][0]["judge_hash"]}                       # every verdict by main's referee
    paid = [e["payload"] for e in record.entries(ex) if e["kind"] == "payout"]
    assert len(paid) == 2 and all(p["cluster"] == "devnet" and p["payout_tx"] and p["fee_tx"] for p in paid)
