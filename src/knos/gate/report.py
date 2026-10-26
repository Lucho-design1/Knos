"""The words Gate posts: one comment (with MARKER, so it is found and edited in place) and one check's title and summary.

Short on purpose: pass or fail, which rule, the counts, the re-run link, the receipt. Every text goes through
`sealed.leaks` before it is posted (knos.gate.run does that); nothing here reads a hidden file."""
from __future__ import annotations

import json

from . import CHECK_NAME, MARKER

INSTALL = "https://github.com/drexthealpha/Knos/blob/main/docs/reference/REFEREE.md"


def title(v: dict) -> str:
    if v.get("skipped"):
        return f"{CHECK_NAME}: not judged ({v['skipped']})"
    if v["passed"]:
        return f"{CHECK_NAME}: passed" + (" (public tests only)" if v["mode"] == "public-tests-only" else "")
    return f"{CHECK_NAME}: refused ({v['rule']})"


def _counts(name: str, c: dict | None) -> str:
    if c is None:
        return ""
    s = f"{c.get('passed', 0)}/{c.get('total', 0)} passed"
    if c.get("failed"):
        s += f", {c['failed']} failed"
    if c.get("errors"):
        s += f", {c['errors']} errors"
    return f"| {name} | {s} |"


def summary(v: dict) -> str:
    lines = [title(v), ""]
    if v.get("skipped"):
        return "\n".join(lines + ["Gate judges pull requests from outside collaborators only (`outside_only: true`)."])
    if v["reasons"]:
        lines += [f"- {r}" for r in v["reasons"][:8]] + [""]
    rows = [r for r in (_counts("hidden tests (contents sealed)", v.get("hidden")), _counts("public tests", v.get("public"))) if r]
    if rows:
        lines += ["| suite | result |", "| --- | --- |", *rows, ""]
    lines.append(f"Cheat checks: {len(v['findings'])} finding(s), library `{v.get('library') or 'local'}`.")
    if v.get("mode") == "public-tests-only":
        lines.append("Public tests only: this repository has no sealed hidden tests.")
    return "\n".join(lines)


def comment(v: dict, receipt: dict | None = None, receipt_url: str = "") -> str:
    head = (v.get("head") or "")[:7]
    out = [MARKER, f"### {title(v)}", ""]
    if v.get("skipped"):
        out.append(f"Commit `{head}`. {v['skipped'].capitalize()}.")
        return "\n".join(out)
    out.append(f"Commit `{head}`. " + ("Every check passed." if v["passed"] else "This pull request was refused:"))
    if not v["passed"]:
        out += [f"- {r}" for r in v["reasons"][:6]]
    out.append("")
    rows = [r for r in (_counts("hidden tests (contents sealed)", v.get("hidden")), _counts("public tests", v.get("public"))) if r]
    if rows:
        out += ["| suite | result |", "| --- | --- |", *rows, ""]
    out.append(f"Cheat checks: {len(v['findings'])} finding(s), library `{v.get('library') or 'local'}`.")
    if v.get("mode") == "public-tests-only":
        out.append("Public tests only: this repository has no sealed hidden tests.")
    links = []
    if v.get("run_url"):
        links.append(f"[re-run]({v['run_url']})")
    if receipt_url:
        links.append(f"[receipt]({receipt_url})")
    links.append(f"[turn on Knos Gate for your repo]({INSTALL})")
    out += ["", " | ".join(links)]
    if receipt is not None:
        out += ["", "<details><summary>Signed receipt (verify offline: <code>knos gate receipt verify FILE</code>)</summary>", "",
                "```json", json.dumps(receipt, indent=1, sort_keys=True), "```", "</details>"]
    out += ["", "<sub>Knos Gate runs tests the author of this pull request cannot see. It shows counts, never their contents.</sub>"]
    return "\n".join(out)
