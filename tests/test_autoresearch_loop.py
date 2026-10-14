"""The autoresearch loop end to end on a smaller copy of examples/autoresearch (SYNTHETIC data): the referee alone
decides, the best result must reproduce on the sealed final set, every step is in the record, Sibyl holds it."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from knos.autoresearch import loop, payout, proposers, recorder, task

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "autoresearch"


def small_task(tmp_path: Path, **over) -> Path:
    root = tmp_path / "task"
    shutil.copytree(EXAMPLE, root)
    spec = json.loads((root / "task.json").read_text(encoding="utf-8"))
    spec["data"].update(n_train=240, n_val=120, n_dev=200, n_final=300)
    spec["time_budget_s"] = 10
    spec.update(over)
    (root / "task.json").write_text(json.dumps(spec), encoding="utf-8")
    return root


class Cheater:
    """Every proposal tries to read the referee's sealed file."""
    name = "cheater"

    def propose(self, ctx):
        src = ctx.best.replace("def main():", "def main():\n    open('../referee/sealed.json')\n", 1)
        return proposers.Candidate({ctx.editable: src}, self.name, "read the sealed file")


def _run(tmp_path, proposer, n, name="out"):
    t = task.load(small_task(tmp_path / f"t-{name}"))
    return loop.run(t, proposer, tmp_path / name, n, use_knos_record=False, say=lambda *_: None), tmp_path / name


def test_the_loop_keeps_only_what_the_referee_accepts_and_graduates_on_sealed_data(tmp_path, knos_home):
    rep, out = _run(tmp_path, proposers.LocalProposer(0), 2)
    assert rep.iterations == 2 and rep.kept >= 1
    assert rep.best_dev > rep.baseline_dev
    f = rep.final
    assert rep.graduated and f["judge_unchanged"]
    assert min(f["lift_per_seed"]) >= f["min_lift"]
    assert len(f["baseline"]["scores"]) == len(f["best"]["scores"]) == 2
    tsv = (out / "results.tsv").read_text(encoding="utf-8").splitlines()
    assert tsv[0].startswith("iteration\t") and len(tsv) == 1 + 1 + 2
    assert (out / "best_train.py").read_text(encoding="utf-8") != (EXAMPLE / "train.py").read_text(encoding="utf-8")
    assert json.loads((out / "summary.json").read_text(encoding="utf-8"))["graduated"] is True
    assert rep.outcome["passed"] and rep.outcome["synthetic"] is True
    assert rep.split["payable"] and sum(p["amount"] for p in rep.split["parts"]) == rep.split["amount"]   # the fee is on top
    assert "no transaction" in rep.split["status"]


def test_every_step_is_in_a_verifiable_record_with_no_source_code(tmp_path, knos_home):
    rep, out = _run(tmp_path, proposers.LocalProposer(0), 2)
    assert rep.record["ok"] and rep.record["broken"] == []
    lines = (out / "record" / "autoresearch-journal.jsonl").read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(x)["kind"] for x in lines]
    assert kinds[:2] == ["paper", "claim"]
    assert kinds.count("experiment") == 3 and {"verdict", "graduation", "split"} <= set(kinds)
    text = "\n".join(lines)
    assert "def fit" not in text and "CONFIG" not in text            # hashes and scores, never the code
    # tamper one line: the chain breaks
    e = json.loads(lines[3])
    e["payload"]["dev_score"] = 1.0
    lines[3] = json.dumps(e, sort_keys=True)
    (out / "record" / "autoresearch-journal.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not recorder.LocalRecord(out / "record").verify()["ok"]


def test_the_record_lives_in_sibyl(tmp_path, knos_home):
    _rep, out = _run(tmp_path, proposers.LocalProposer(0), 1)
    st = recorder.LocalRecord(out / "record").store
    assert len(st.events(limit=100)) >= 3                             # COLD: experiments, verdict...
    assert st.all("record_claim")                                     # WARM: the research claim
    assert (out / "record" / "sibyl.db").exists()


def test_a_cheating_agent_is_refused_every_time_and_nothing_is_paid(tmp_path, knos_home):
    rep, out = _run(tmp_path, Cheater(), 2)
    assert rep.refused == 2 and rep.kept == 0
    assert not rep.graduated and "no change was kept" in rep.final["reasons"]
    assert rep.split["payable"] is False and rep.split["parts"] == []
    kinds = [json.loads(x)["kind"] for x in (out / "record" / "autoresearch-journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert kinds.count("refusal") == 2 and kinds.count("cheat") >= 2 and "graduation" not in kinds


def test_the_same_seed_gives_the_same_run(tmp_path, knos_home):
    a, _ = _run(tmp_path, proposers.LocalProposer(7), 3, "a")
    b, _ = _run(tmp_path, proposers.LocalProposer(7), 3, "b")
    assert [(h["change"], h["decision"]) for h in a.history] == [(h["change"], h["decision"]) for h in b.history]
    assert a.final["best"]["scores"] == b.final["best"]["scores"]


def test_the_agent_never_sees_a_hidden_score(tmp_path, knos_home):
    rep, _ = _run(tmp_path, proposers.LocalProposer(0), 2)
    for h in rep.history:
        assert set(h) == {"iteration", "agent", "change", "decision", "reasons", "reported"}
        assert set(h["reported"]) <= {"val_accuracy"}


def test_split_plan_sums_exactly_and_divides_the_agents_share_by_kept_changes(tmp_path):
    t = task.load(small_task(tmp_path, bounty={"amount": 1_000_001, "currency": "test", "shares": {"researcher": 6000, "agent": 2500, "referee": 1500}}))
    plan = payout.split_plan(t, {"a": 2, "b": 1}, graduated=True)
    assert sum(p["amount"] for p in plan["parts"]) == 1_000_001
    assert plan["fee"] is None or plan["funder_pays"] == 1_000_001 + plan["fee"]
    agents = {p["who"]: p["amount"] for p in plan["parts"] if p["role"] == "agent"}
    assert set(agents) == {"a", "b"} and agents["a"] > agents["b"]
    assert payout.split_plan(t, {"a": 1}, graduated=False)["payable"] is False


@pytest.mark.parametrize("n", [0, 1, 2, 5])
def test_merkle_root_is_stable(n):
    hs = [f"{i:064x}" for i in range(n)]
    assert recorder.merkle_root(hs) == recorder.merkle_root(list(hs))
    assert (recorder.merkle_root(hs) == hashlib.sha256(b"").hexdigest()) == (n == 0)


def test_a_role_the_fee_config_lacks_does_not_crash_the_plan(tmp_path):
    t = task.load(small_task(tmp_path, bounty={"amount": 500, "currency": "test", "shares": {"inventor": 1, "agent": 1}}))
    plan = payout.split_plan(t, {"a": 1}, graduated=True)
    assert plan["payable"] and sum(p["amount"] for p in plan["parts"]) == 500


class Noisy:
    """An agent whose change line and output carry text a public record refuses (a home path, an address)."""
    name = "noisy"

    def __init__(self):
        self.inner = proposers.LocalProposer(0)

    def propose(self, ctx):
        c = self.inner.propose(ctx)
        return c and proposers.Candidate(c.files, self.name, "tried /home/alice/x.py, mail bob@example.com")


def test_agent_free_text_is_hashed_not_refused_and_the_run_completes(tmp_path, knos_home):
    rep, out = _run(tmp_path, Noisy(), 1)
    assert rep.record["ok"] and rep.iterations == 1
    text = (out / "record" / "autoresearch-journal.jsonl").read_text(encoding="utf-8")
    assert "alice" not in text and "example.com" not in text and "sha256:" in text
    assert recorder.sanitize({"change": "lr: 0.05 -> 0.1"}) == {"change": "lr: 0.05 -> 0.1"}


def test_the_fallback_merkle_root_is_the_records_own():
    hs = [f"{i:064x}" for i in range(7)]
    merkle = pytest.importorskip("knos.record.merkle")
    assert recorder.merkle_root(hs) == merkle.root(hs) and recorder.merkle_root([]) == merkle.root([])


def test_the_fallback_verifier_catches_a_dropped_or_reordered_line(tmp_path, knos_home):
    _rep, out = _run(tmp_path, proposers.LocalProposer(0), 1)
    p = out / "record" / "autoresearch-journal.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join(lines[:2] + lines[3:]) + "\n", encoding="utf-8")
    assert not recorder.LocalRecord(out / "record").verify()["ok"]
    p.write_text("\n".join([lines[1], lines[0]] + lines[2:]) + "\n", encoding="utf-8")
    assert not recorder.LocalRecord(out / "record").verify()["ok"]
    p.write_text("\n".join(lines + ["{not json"]) + "\n", encoding="utf-8")
    assert recorder.LocalRecord(out / "record").verify()["broken"] == [len(lines)]


def test_anchor_goes_through_knos_record_with_a_fake_send_and_a_failure_is_reported(tmp_path, knos_home):
    record = pytest.importorskip("knos.record")
    if not hasattr(record, "anchor"):
        pytest.skip("knos.record without anchor")
    t = task.load(small_task(tmp_path))
    sent = []
    fake = lambda memo: sent.append(memo) or {"tx": "5" * 88, "signer": "1" * 44, "slot": 1}  # noqa: E731
    rep = loop.run(t, proposers.LocalProposer(0), tmp_path / "o", 1, record_root=tmp_path / "rec", anchor=True,
                   anchor_send=fake, say=lambda *_: None)
    assert rep.anchor["anchored"] is True and len(sent) == 1 and (tmp_path / "o" / "summary.json").exists()

    def broken(memo):
        raise RuntimeError("devnet unreachable")
    rep2 = loop.run(t, proposers.LocalProposer(0), tmp_path / "o2", 1, record_root=tmp_path / "rec2", anchor=True,
                    anchor_send=broken, say=lambda *_: None)
    assert rep2.anchor == {"anchored": False, "why": "RuntimeError: devnet unreachable"}
    assert (tmp_path / "o2" / "summary.json").exists()
