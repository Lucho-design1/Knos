"""Works: does the submitted work do what the sealed spec asks, judged by a referee the worker cannot reach?

In order, and the first that fails decides (each is said in `reasons`):

    1. sealed tests   the hidden bundle's hash is the seal's `spec_hash` (nobody swapped the tests after sealing)
    2. locked judge   the running judging code's hash is the seal's `judge_hash` (the referee is main's, not the PR's)
    3. cheat rules    the cheat library on the change (knos.cheats): any refusing rule refuses, and no pull request
                      code has run yet
    4. hidden tests   knos.judge.judge on the hidden bundle: fail-to-pass, sentinel and canary, sandbox, overlay of
                      the base's tests (the judge is used as it is, never weakened)
    5. re-run         the same judgment again, fresh (another process, another seed for any generated inputs: a
                      black-box bundle draws its own); the verdicts must agree, and a numeric metric must be within
                      the seal's tolerance. A second machine is a `judge_fn` that judges there.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .. import cheats as _cheats
from .check import Check, write
from .seal import judge_hash


def within_tolerance(a: float, b: float, abs_tol: float = 0.0, rel_tol: float = 0.0) -> bool:
    a, b = float(a), float(b)
    return abs(a - b) <= max(float(abs_tol), float(rel_tol) * max(abs(a), abs(b)))


def rerun_agrees(first: dict, second: dict, tolerance: dict | None = None) -> tuple[bool, list[str]]:
    """Whether two verdicts on the same artifact agree: the same pass/fail, the same acceptance bundle, and a metric
    (verdict["metric"], when both have one) within {"abs", "rel"} of each other."""
    why = []
    if bool(first.get("passed")) != bool(second.get("passed")):
        why.append(f"re-run disagrees: first {'passed' if first.get('passed') else 'refused'}, "
                   f"again {'passed' if second.get('passed') else 'refused'}")
    if first.get("checks_hash") and second.get("checks_hash") and first["checks_hash"] != second["checks_hash"]:
        why.append("re-run judged another acceptance bundle")
    if first.get("metric") is not None or second.get("metric") is not None:
        tol = tolerance or {}
        if first.get("metric") is None or second.get("metric") is None:
            why.append("re-run: the metric is missing from one run")
        elif not within_tolerance(first["metric"], second["metric"], tol.get("abs", 0.0), tol.get("rel", 0.0)):
            why.append(f"re-run metric {second['metric']} is not within tolerance of {first['metric']} "
                       f"(abs {tol.get('abs', 0.0)}, rel {tol.get('rel', 0.0)})")
    return not why, why


def _with_hidden(base: Path, hidden: Path, issue: str, into: Path) -> Path:
    """A copy of the base with the sealed bundle in place at .knos/acceptance/<issue> (the worker's tree never has it)."""
    shutil.copytree(base, into, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules"), symlinks=True)
    dest = into / ".knos" / "acceptance" / issue
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(hidden, dest)
    return into


def works(base_dir, pr_dir, seal: dict, *, hidden_dir=None, changed=None, sandbox: str = "auto", reruns: int | None = None,
          judge_fn=None, metric=None, core=(), scan: bool = True, cfg: dict | None = None, record_root=None,
          record: bool = False, domain: str = "code") -> Check:
    """The Works test. `seal`: referee.seal(...). `hidden_dir`: the sealed bundle when it is kept outside the base
    (default: the base's own .knos/acceptance/<issue>). `judge_fn(base, pr, cfg, changed=..., sandbox=...)`: the judge
    (default knos.judge.judge); `metric(verdict) -> float`: a number the re-run must reproduce. `scan=False` skips the
    cheat rules (only to show what the sealed tests catch on their own). `record`: write the verification and every
    cheat caught to Knos Record."""
    from .. import judge as J
    base, pr = Path(base_dir), Path(pr_dir)
    issue = str(seal.get("issue", ""))
    ev: dict = {"issue": issue, "spec_hash": seal.get("spec_hash"), "judge_hash": seal.get("judge_hash")}
    findings: list = []

    def done(passed: bool, reasons: list[str]) -> Check:
        c = Check("works", passed, reasons, ev, findings)
        if record:
            _record(c, seal, domain, record_root)
        return c

    tmp = Path(tempfile.mkdtemp(prefix="knos-referee-"))
    try:
        bundle = Path(hidden_dir) if hidden_dir is not None else base / ".knos" / "acceptance" / issue
        try:
            have = J.checks_hash(bundle)
        except ValueError as why:
            return done(False, [f"sealed tests: {why}"])
        ev["bundle_hash"] = have
        if have != seal.get("spec_hash"):
            findings.append(_cheats.Finding("sealed_tests_changed", "sealed_tests_changed", "", "the hidden bundle's hash is not the sealed one"))
            return done(False, [f"sealed tests changed: the bundle hashes {have[:16]}, the seal says {str(seal.get('spec_hash'))[:16]}"])
        running = judge_hash()
        ev["running_judge_hash"] = running
        if running != seal.get("judge_hash"):
            findings.append(_cheats.Finding("judge_drift", "judge_drift", "", "the running judging code is not the sealed one"))
            return done(False, [f"locked judge: the running judging code hashes {running[:16]}, the seal says "
                                f"{str(seal.get('judge_hash'))[:16]}; judge with the referee the seal names"])
        terms = dict(cfg) if cfg is not None else _proof(base)
        if seal.get("test_dirs"):
            terms["test_dirs"] = list(seal["test_dirs"])
        changed = J.changed_files(base, pr) if changed is None else sorted(changed)
        ev["changed"] = changed
        if scan:
            findings[:] = _cheats.scan(base, pr, changed=changed, scope=seal.get("scope") or (), core=core, terms=terms)
            ev["cheat_rules"] = len(_cheats.rules(kind="change"))
            if _cheats.refused(findings):
                return done(False, [f"cheat rule {f.rule} ({f.category}){': ' + f.path if f.path else ''}: {f.detail}"
                                    for f in findings if f.severity == "refuse"])
        judged_base = _with_hidden(base, bundle, issue, tmp / "base") if hidden_dir is not None else base
        judge_fn = judge_fn or J.judge
        run_cfg = {**terms, "issue": issue}

        def once() -> dict:
            v = judge_fn(judged_base, pr, run_cfg, changed=changed, sandbox=sandbox)
            if metric is not None and v.get("metric") is None:
                try:
                    v = {**v, "metric": float(metric(v))}
                except Exception as why:  # noqa: BLE001 - a metric that cannot be read is no metric
                    v = {**v, "metric": None, "metric_error": str(why)[:200]}
            return v
        first = once()
        ev["verdict"] = _slim(first)
        if first.get("checks_hash") and first["checks_hash"] != seal.get("spec_hash"):
            return done(False, ["the judge ran another bundle than the sealed one"])
        if not first.get("passed"):
            word = first.get("verdict", "rejected")
            return done(False, [f"hidden tests: {word}: {r}" for r in first.get("reasons", [])] or [f"hidden tests: {word}"])
        n = int(seal.get("reruns", 1) if reruns is None else reruns)
        ev["reruns"] = []
        for _ in range(max(0, n)):
            again = once()
            ok, why = rerun_agrees(first, again, seal.get("tolerance"))
            ev["reruns"].append({"agree": ok, "verdict": _slim(again)})
            if not ok:
                findings.append(_cheats.Finding("rerun_mismatch", "rerun_mismatch", "", "; ".join(why)))
                return done(False, why)
        return done(True, [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _proof(base: Path) -> dict:
    from ..judge import proof_config
    p = base / ".knos" / "proof.toml"
    got = proof_config(p.read_text(encoding="utf-8")) if p.is_file() else {}
    return {k: v for k, v in got.items() if not str(k).startswith("_")}


def _slim(v: dict) -> dict:
    keep = ("passed", "verdict", "checks_hash", "reasons", "notes", "assurance", "judged_in", "metric")
    out = {k: v[k] for k in keep if k in v}
    art = (v.get("evidence") or {}).get("artifact")
    if art:
        out["artifact"] = art
    return out


def _record(c: Check, seal: dict, domain: str, root) -> None:
    try:
        got = write("verification", {"spec_hash": seal.get("spec_hash"), "judge_hash": seal.get("judge_hash"),
                                     "test": "works", "passed": c.passed,
                                     "cheats": sorted({f.category for f in c.cheats})}, domain=domain, root=root)
        for f in c.cheats:
            write("cheat", {"spec_hash": seal.get("spec_hash"), "cheat": f.category, "rule": f.rule,
                            "severity": f.severity}, domain=domain, root=root)
        c.evidence["recorded"] = got is not None
    except ValueError as why:          # Record refuses anything that looks like a secret: said, never hidden
        c.evidence["recorded"] = f"refused by Knos Record: {why}"
