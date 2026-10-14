"""One pull request's Gate verdict, as data: what passed, what failed first, and what the maintainer asked to happen.

The order of the reasons is fixed: a refused cheat first (the tests of a pull request that edits them say nothing),
then the hidden tests, then the public ones. `rule` is the first reason's id, the one the check and the comment name.
No field holds a test's name, message or output: counts only."""
from __future__ import annotations

from . import sealed

OUTSIDE_ROLES = ("OWNER", "MEMBER", "COLLABORATOR")


def outside(author_association: str | None) -> bool:
    """GitHub's author_association: an OWNER, MEMBER or COLLABORATOR is inside; everyone else is outside."""
    return (author_association or "NONE").upper() not in OUTSIDE_ROLES


def decide(cfg: dict, findings: list[dict], hidden: dict | None, public: dict | None, *, repo: str, pr: int, head: str,
           base: str, run_url: str = "", library: str = "", spec_hash: str = "", error: str = "") -> dict:
    reasons: list[tuple[str, str]] = []
    for f in findings:
        if f.get("severity", "refuse") == "refuse":
            reasons.append((f["rule"], f"{f['category']}: {f['detail']}" + (f" ({f['path']})" if f.get("path") and f["path"] not in f["detail"] else "")))
    if error:
        reasons.append(("gate.error", error))
    if hidden is not None and not sealed.passed(hidden):
        reasons.append(("gate.hidden_tests_failed", _said("hidden", hidden)))
    if public is not None and not sealed.passed(public):
        reasons.append(("gate.public_tests_failed", _said("public", public)))
    mode = "hidden" if cfg.get("hidden_tests") else "public-tests-only"
    return {"type": "knos.gate-verdict", "version": 1, "repo": repo, "pr": int(pr), "head": head, "base": base,
            "passed": not reasons, "rule": reasons[0][0] if reasons else "", "reasons": [r for _, r in reasons],
            "mode": mode, "spec_hash": spec_hash or ((cfg.get("hidden_tests") or {}).get("sha256") or ""),
            "hidden": _strip(hidden), "public": _strip(public), "findings": findings, "library": library,
            "run_url": run_url, "on_fail": cfg.get("on_fail", "comment")}


def _strip(c: dict | None) -> dict | None:
    if c is None:
        return None
    return {k: c[k] for k in ("total", "passed", "failed", "errors", "skipped", "sandbox", "timed_out") if k in c}


def _said(which: str, c: dict) -> str:
    if c.get("timed_out"):
        return f"the {which} tests did not finish in time"
    if not c.get("total"):
        return f"the {which} tests did not run (no result was reported)"
    return f"{which} tests: {c.get('passed', 0)} of {c.get('total', 0)} passed" + \
        (f", {c['failed']} failed" if c.get("failed") else "") + (f", {c['errors']} errors" if c.get("errors") else "")


def actions(v: dict, cfg: dict) -> dict:
    """What happens to the pull request: {close, add_labels, remove_labels}."""
    if v.get("skipped"):
        return {"close": False, "add_labels": [], "remove_labels": []}
    if v["passed"]:
        return {"close": False, "add_labels": [cfg["pass_label"]] if cfg.get("pass_label") else [],
                "remove_labels": [cfg["label"]] if cfg.get("label") else []}
    on = cfg.get("on_fail", "comment")
    labels = [cfg["label"]] if on in ("label", "close") and cfg.get("label") else []
    return {"close": on == "close", "add_labels": labels,
            "remove_labels": [cfg["pass_label"]] if cfg.get("pass_label") else []}


def skipped(repo: str, pr: int, head: str, base: str, why: str) -> dict:
    """A pull request Gate does not judge (an inside author with outside_only): a passing check that says so."""
    return {"type": "knos.gate-verdict", "version": 1, "repo": repo, "pr": int(pr), "head": head, "base": base,
            "passed": True, "skipped": why, "rule": "", "reasons": [], "mode": "skipped", "spec_hash": "",
            "hidden": None, "public": None, "findings": [], "library": "", "run_url": "", "on_fail": "comment"}
