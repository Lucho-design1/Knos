"""The golden path, end to end: Nemotron proposes, the referee decides, Ultra explains refusals, Tavily checks
provenance and finds a new cheat pattern that the referee must accept on its own test, and the panel shows the bill.

    1  autoresearch   Nemotron 3 Super is the proposer of knos.autoresearch on examples/autoresearch (synthetic data);
                      the locked referee judges every proposal on sealed data (two seeds = the re-run) and graduates
                      the best on a second sealed set
    2  self           Nemotron 3 Super writes diffs for a knos.self target (targets.yml); the referee's static half
                      (`knos self check-pr`) screens each; a diff that passes goes to `knos self run` (the founder's loop)
    3  explain        each refusal gets Nemotron 3 Ultra's paragraph; the verdict field is copied from the referee
    4  provenance     Tavily searches the best candidate's most distinctive lines (advisory)
    5  new rules      Tavily + Super draft one cheat rule; rules_intake accepts it only on its known cases
    6  panel          panel.json + panel.html in --out

With no NEBIUS_API_KEY / TAVILY_API_KEY every model and search reply is MOCK (labelled); the referee's runs are real.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..autoresearch import loop as ar_loop
from ..autoresearch import task as ar_task
from ..self import config as self_config
from . import coder, explain, mock, panel, rerun, rules_intake, sources, tavily
from .tokenfactory import TokenFactory


def run_demo(root: Path, out: Path, *, iterations: int = 4, task_dir: Path | None = None, target: str = "mcp-cold-start",
             tf: TokenFactory | None = None, tv: tavily.Tavily | None = None, say=print) -> dict:
    root, out = Path(root), Path(out)
    tf = tf or TokenFactory(responder=mock.responder())
    tv = tv or tavily.Tavily(responder=mock.tavily_responder)
    modes = {"token_factory": tf.mode, "tavily": tv.mode}
    reruns = rerun.backend()
    say(f"Token Factory: {tf.mode}; Tavily: {tv.mode}; re-runs: {reruns['backend']}")
    if "mock" in modes.values():
        say(sources.MOCK + ": model and search replies are made locally; the referee's runs are real")

    # 1. autoresearch with Nemotron 3 Super as the proposer
    t = ar_task.load(task_dir or root / "examples" / "autoresearch")
    proposer = coder.NemotronProposer(tf)
    rep = ar_loop.run(t, proposer, out / "autoresearch", iterations, record_root=out / "record", say=say)
    experiments = [{k: h[k] for k in ("iteration", "agent", "change", "decision")} for h in rep.history]
    cheats_out = []

    # 3a. every autoresearch refusal explained (advisory)
    for h in rep.history:
        if h["decision"] == "refused":
            findings = [{"rule": r.split()[1] if r.startswith("refused:") else "", "category": "", "detail": r} for r in h["reasons"]]
            for f in findings:
                f["category"] = {"AR-SEALED": "data_tampering", "AR-IMPORT": "runner_tampering",
                                 "AR-SCOPE": "out_of_scope"}.get(f["rule"], "")
            e = explain.explain(tf, verdict="refused", findings=findings, subject=h["change"])
            cheats_out.append({"where": f"autoresearch #{h['iteration']}", **e})

    # 2. the self loop's coder on one target, screened by the referee's static half
    cfg = self_config.load(root)
    tgt = self_config.target(cfg, target)
    self_runs = []
    for _ in range(2):
        d = coder.self_diff(tf, tgt, root)
        screen = coder.prescreen(d["diff"], cfg, tgt)
        self_runs.append({"change": d["change"], "refused": screen["refused"], "paths": screen["paths"],
                          "rules": sorted({f["rule"] for f in screen["findings"]})})
        experiments.append({"iteration": f"self-{len(self_runs)}", "agent": proposer.name, "change": d["change"],
                            "decision": "refused" if screen["refused"] else "passes check-pr (next: knos self run)"})
        if screen["refused"]:
            e = explain.explain(tf, verdict="refused", findings=screen["findings"], subject=d["diff"])
            cheats_out.append({"where": f"knos self {target}", **e})
        say(f"self {target}: {'refused' if screen['refused'] else 'passes check-pr'}  {d['change']}")

    # 4. provenance of the best candidate (advisory)
    best_src = (out / "autoresearch" / f"best_{t.editable}").read_text(encoding="utf-8")
    prov = tavily.provenance(tv, best_src)
    say(f"provenance: {prov['finding']} ({prov['checked_lines']} lines searched)")

    # 5. a new cheat pattern from the web, accepted or not by the referee's own test
    rules_log = []
    proposal, draft_log = rules_intake.draft_from_web(tv, tf)
    if proposal is not None:
        decision = rules_intake.accept(proposal)
        rules_log.append({**decision, "proposal": rules_intake.proposal_dict(proposal), "draft": draft_log})
        say(f"rule {proposal.id}: {'accepted' if decision['accepted'] else 'rejected'} {'; '.join(decision['reasons'])}")
    else:
        rules_log.append({"id": "(none)", "accepted": False, "reasons": [draft_log.get("error", "no draft")], "draft": draft_log})

    m = panel.metrics(tf.calls, tv.calls, kept=rep.kept, graduated=rep.graduated, refused_ar=rep.refused,
                      refused_self=sum(r["refused"] for r in self_runs), rules_accepted=sum(bool(r["accepted"]) for r in rules_log),
                      rules_proposed=sum(r.get("id") != "(none)" for r in rules_log), modes=modes)
    data = {"generated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "metrics": m, "experiments": experiments,
            "cheats": cheats_out, "self": self_runs, "provenance": prov, "rules": rules_log, "reruns": reruns,
            "autoresearch": {"spec_hash": rep.spec_hash, "baseline_dev": rep.baseline_dev, "best_dev": rep.best_dev,
                             "graduated": rep.graduated, "lift": rep.final.get("lift"), "reasons": rep.final.get("reasons"),
                             "record": rep.record, "synthetic": True},
            "calls": [r.to_dict() for r in tf.calls], "searches": [s.to_dict() for s in tv.calls],
            "sources": sources.SOURCES, "sources_read": sources.FETCHED}
    panel.write(out, data)
    say(panel.text(data))
    return data
