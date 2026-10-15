"""The loop: propose, judge, keep if better, record; then graduate on data nobody saw.

    seal     the spec hash (program, idea, terms, baseline, sealed data's hash, judging code's hash) -> Record first
    0        the baseline is judged on hidden_dev: the score to beat
    1..N     the proposer offers one change to the one file; the referee judges it on hidden_dev (two seeds);
             kept only when it passes and beats the best by more than keep_delta. Each experiment -> Record
             (kind experiment; plus one cheat entry per finding and a refusal when refused)
    final    baseline and best on hidden_final, both seeds -> Record (verdict, graduation)
    payout   when graduated: the outcome and the split PLAN -> Record (kind split); nothing is sent

Outputs in <out>: results.tsv (one row per experiment), best_<editable>, summary.json.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import payout
from .judge import LocalJudge
from .proposers import Context
from .recorder import Recorder
from .task import Task


@dataclass
class Report:
    spec_hash: str
    judge_backend: str
    record_backend: str
    proposer: str
    iterations: int = 0
    kept: int = 0
    discarded: int = 0
    refused: int = 0
    failed: int = 0
    baseline_dev: float | None = None
    best_dev: float | None = None
    final: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)
    split: dict = field(default_factory=dict)
    record: dict = field(default_factory=dict)
    anchor: dict = field(default_factory=dict)
    wall_s: float = 0.0
    history: list[dict] = field(default_factory=list)

    @property
    def graduated(self) -> bool:
        return bool(self.final.get("graduated"))

    def to_dict(self) -> dict:
        return asdict(self) | {"graduated": self.graduated}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _r(x):
    return None if x is None else round(x, 6)


def run(task: Task, proposer, out: Path, iterations: int = 12, record_root: Path | None = None, judge=None,
        use_knos_record: bool = True, anchor: bool = False, say=print, anchor_keypair=None, anchor_send=None) -> Report:
    t0 = time.monotonic()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    judge = judge or LocalJudge(task)
    seal = judge.seal()
    claim_id = "ar-" + seal["spec_hash"][:16]
    rec = Recorder(record_root or out / "record", claim_id, use_knos_record)
    rep = Report(seal["spec_hash"], judge.backend, rec.backend, getattr(proposer, "name", type(proposer).__name__))
    synthetic = bool(task.spec.get("synthetic"))

    rec.paper("ar-program-" + _sha(task.program)[:16], {"title": task.spec["name"], "program_sha256": _sha(task.program),
                                                         "idea_sha256": _sha(task.idea), "synthetic": synthetic})
    rec.claim({"spec_hash": seal["spec_hash"], "judge_hash": seal["judge_hash"], "task": task.spec["name"],
               "metric": task.spec["metric"], "status": "open", "synthetic": synthetic})
    say(f"sealed {seal['spec_hash'][:16]}  judge {seal['judge_hash'][:16]}  record: {rec.backend}")

    base_v = judge.judge({task.editable: task.baseline}, None, stage="dev")
    if not base_v.passed:
        raise RuntimeError("the baseline itself fails the referee: " + "; ".join(base_v.reasons))
    best_src, best = task.baseline, base_v.score
    rep.baseline_dev = _r(best)
    rec.event("experiment", {"iteration": 0, "agent": "researcher", "change": "baseline", "decision": "baseline",
                             "dev_score": _r(best), "scores": [_r(s) for s in base_v.scores], "spec_hash": seal["spec_hash"],
                             "synthetic": synthetic})
    rows = [("0", "researcher", "baseline", f"{best:.4f}", f"{base_v.reported.get('val_accuracy', float('nan')):.4f}",
             f"{base_v.wall_s:.2f}", "baseline")]
    say(f"#0 baseline  dev {best:.4f}")
    kept_by: Counter[str] = Counter()

    for i in range(1, iterations + 1):
        ctx = Context(task.program, task.idea, task.editable, best_src, rep.history)
        cand = proposer.propose(ctx)
        if cand is None:
            say(f"proposer has nothing left to try after {i - 1} experiments")
            break
        v = judge.judge(cand.files, best_src, stage="dev")
        rep.iterations = i
        if v.refused:
            decision = "refused"
            rep.refused += 1
        elif not v.passed:
            decision = "failed"
            rep.failed += 1
        elif task.better(v.score, best, task.spec["keep_delta"]):
            decision = "kept"
            rep.kept += 1
            best_src, best = cand.files[task.editable], v.score
            kept_by[cand.agent] += 1
        else:
            decision = "discarded"
            rep.discarded += 1
        entry = {"iteration": i, "agent": cand.agent, "change": cand.change, "decision": decision,
                 "dev_score": _r(v.score), "scores": [_r(s) for s in v.scores], "best_dev": _r(best),
                 "candidate_sha256": _sha(cand.files.get(task.editable, "")), "cheats": [c.category for c in v.cheats],
                 "spec_hash": seal["spec_hash"], "synthetic": synthetic}
        rec.event("experiment", entry)
        for c in v.cheats:
            rec.event("cheat", {"iteration": i, "rule": c.rule, "cheat": c.category, "severity": c.severity,
                                "spec_hash": seal["spec_hash"]})
        if decision == "refused":
            rec.event("refusal", {"iteration": i, "reasons": v.reasons[:5], "spec_hash": seal["spec_hash"]})
        # what the agent is told: its change, its own val score, the decision and reasons. No hidden score.
        rep.history.append({"iteration": i, "agent": cand.agent, "change": cand.change, "decision": decision,
                            "reasons": v.reasons[:3], "reported": v.reported})
        rows.append((str(i), cand.agent, decision, "" if v.score is None else f"{v.score:.4f}",
                     f"{v.reported['val_accuracy']:.4f}" if "val_accuracy" in v.reported else "",
                     f"{v.wall_s:.2f}", cand.change))
        say(f"#{i} {decision:9s} dev {'-' if v.score is None else f'{v.score:.4f}'}  best {best:.4f}  {cand.change}")

    rep.best_dev = _r(best)
    final = judge.final(task.baseline, best_src)
    rep.final = final
    rec.event("verdict", {"stage": "graduation", "passed": final["graduated"], "reasons": final["reasons"][:5],
                          "baseline_final": [_r(s) for s in final["baseline"]["scores"]],
                          "best_final": [_r(s) for s in final["best"]["scores"]], "lift": _r(final["lift"]),
                          "min_lift": final["min_lift"], "judge_unchanged": final["judge_unchanged"],
                          "spec_hash": seal["spec_hash"], "synthetic": synthetic})
    rep.outcome = payout.outcome(task, seal, final)
    rep.split = payout.split_plan(task, dict(kept_by), final["graduated"])
    if final["graduated"]:
        rec.event("graduation", {"spec_hash": seal["spec_hash"], "lift": _r(final["lift"]), "best_sha256": _sha(best_src),
                                 "synthetic": synthetic})
        rec.event("split", {"spec_hash": seal["spec_hash"], "status": rep.split["status"], "amount": rep.split["amount"],
                            "fee": rep.split.get("fee", 0), "parts": [{"role": p["role"], "amount": p["amount"]} for p in rep.split["parts"]],
                            "cluster": "devnet", "synthetic": synthetic})
    rec.claim({"spec_hash": seal["spec_hash"], "status": "graduated" if final["graduated"] else "not graduated",
               "experiments": rep.iterations, "kept": rep.kept, "lift": _r(final["lift"]), "synthetic": synthetic})
    rep.record = rec.verify()
    if anchor:
        rep.anchor = rec.anchor(anchor_keypair, anchor_send)
    rep.wall_s = round(time.monotonic() - t0, 2)

    (out / f"best_{task.editable}").write_text(best_src, encoding="utf-8")
    with (out / "results.tsv").open("w", encoding="utf-8") as f:
        f.write("iteration\tagent\tdecision\tdev_score\tval_reported\twall_s\tchange\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    (out / "summary.json").write_text(json.dumps(rep.to_dict(), indent=2, default=str) + "\n", encoding="utf-8")
    return rep
