"""Gate's cheat findings where a maintainer already looks: GitHub code scanning (SARIF 2.1.0) and check-run annotations.

    sarif(verdict, diff)        a SARIF 2.1.0 log of the refused cheats: one result per finding, at the first line the
                                pull request changed in that file, with a fingerprint that does not move when the pull
                                request gets a new commit (so GitHub keeps ONE alert per cheat, not one per push)
    annotations(verdict, diff)  the same findings as check-run annotations (path, line, level, message), at most
                                MAX_ANNOTATIONS, for the Checks API (App mode) and for `::error file=...` lines (Action mode)
    gzip64(log)                 the `sarif` field of POST /repos/{owner}/{repo}/code-scanning/sarifs: gzip, then base64

Only what the verdict already says leaves here (rule, category, path, detail): never a hidden test's name or line,
and `knos.gate.run` checks this text against the hidden files' lines before it is written, as it does the comment.
GitHub's docs: https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning
and https://docs.github.com/en/rest/code-scanning/code-scanning#upload-an-analysis-as-sarif-data (read 14 Oct 2026)."""
# No `from __future__ import annotations` here: the module's own function `annotations` would shadow that name.
import base64
import gzip
import hashlib
import json
import re
from typing import cast

from . import CHECK_NAME
from .cheatlib import RULES, changed_files

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFO = "https://github.com/drexthealpha/Knos/blob/main/docs/reference/REFEREE.md"
CATEGORY = "knos-gate"                 # runAutomationDetails.id: Gate's analyses stay apart from CodeQL's
MAX_ANNOTATIONS = 50                   # the Checks API takes at most 50 annotations a request
FINGERPRINT = "knosFinding/v1"
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def first_lines(diff: str) -> dict[str, int]:
    """{path: the first line the pull request added or changed in it, in the head's copy}; a file the diff only
    removes from, or removes, has none (its finding is placed at line 1)."""
    out: dict[str, int] = {}
    paths = [f["path"] for f in changed_files(diff)]
    i, cur, line = -1, None, 0
    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            i += 1
            cur = paths[i] if i < len(paths) else None
            continue
        m = _HUNK.match(raw)
        if m:
            line = int(m.group(1))
            continue
        if cur is None or raw.startswith(("+++", "---")) or not line:
            continue
        if raw.startswith("+"):
            out.setdefault(cur, line)
            line += 1
        elif raw.startswith(" ") or raw == "":     # context (an empty line is a blank context line whose space was trimmed)
            line += 1
    return out


def _refused(verdict: dict) -> list[dict]:
    return [f for f in verdict.get("findings") or [] if f.get("severity", "refuse") == "refuse"]


def _where(f: dict, lines: dict[str, int]) -> tuple[str, int]:
    path = str(f.get("path") or "")
    return path, int(f.get("line") or lines.get(path, 1))


def fingerprint(f: dict) -> str:
    """The same cheat at the same path is the same alert across pushes: rule and path, not line or commit."""
    return hashlib.sha256(f"{f.get('rule')}\x00{f.get('path') or ''}".encode()).hexdigest()


def sarif(verdict: dict, diff: str = "", version: str = "") -> dict:
    """A SARIF 2.1.0 log of the verdict's refused findings. An empty `results` list is meaningful: uploading it closes
    the alerts an earlier push opened (GitHub marks an alert fixed when the same category no longer reports it)."""
    lines = first_lines(diff) if diff else {}
    found = _refused(verdict)
    ids = sorted({f["rule"] for f in found} | set(RULES))
    rules = []
    for rid in ids:
        # a refused finding names its category and detail (knos.gate.cheatlib's Finding): both are str
        cat, said = cast("tuple[str, str]", RULES.get(rid, (next((f.get("category") for f in found if f["rule"] == rid), "cheat"), "")))
        said = said or cast(str, next((f.get("detail") for f in found if f["rule"] == rid), rid))
        rules.append({"id": rid, "name": "".join(w.capitalize() for w in re.split(r"[^A-Za-z0-9]+", cat) if w) or "Cheat",
                      "shortDescription": {"text": f"Knos Gate: {cat.replace('_', ' ')}"},
                      "fullDescription": {"text": f"The pull request {said}." if not said.endswith(".") else said},
                      "helpUri": INFO, "help": {"text": f"Refused by Knos Gate ({rid}). See {INFO}."},
                      "defaultConfiguration": {"level": "error"},
                      "properties": {"tags": ["security", "knos-gate", cat], "precision": "high",
                                     "security-severity": "7.0"}})
    index = {r["id"]: n for n, r in enumerate(rules)}
    results = []
    for f in found:
        path, line = _where(f, lines)
        loc = {"physicalLocation": {"artifactLocation": {"uri": path or ".knos/gate.yml", "uriBaseId": "%SRCROOT%"},
                                    "region": {"startLine": max(1, line)}}}
        results.append({"ruleId": f["rule"], "ruleIndex": index[f["rule"]], "level": "error",
                        "message": {"text": f"{f.get('category', 'cheat')}: {f.get('detail', '')}"[:1000]},
                        "locations": [loc], "partialFingerprints": {FINGERPRINT: fingerprint(f)}})
    return {"$schema": SCHEMA, "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": CHECK_NAME, "informationUri": INFO, "semanticVersion": version or "0.0.0",
                                          "rules": rules}},
                      "automationDetails": {"id": f"{CATEGORY}/"},
                      "results": results,
                      "properties": {"repo": verdict.get("repo", ""), "pr": verdict.get("pr"), "head": verdict.get("head", ""),
                                     "passed": bool(verdict.get("passed"))}}]}


def annotations(verdict: dict, diff: str = "") -> list[dict]:
    """The refused findings as Checks API annotations (output.annotations): at most MAX_ANNOTATIONS."""
    lines = first_lines(diff) if diff else {}
    out = []
    for f in _refused(verdict)[:MAX_ANNOTATIONS]:
        path, line = _where(f, lines)
        out.append({"path": path or ".knos/gate.yml", "start_line": max(1, line), "end_line": max(1, line),
                    "annotation_level": "failure", "title": f"Knos Gate: {f.get('category', 'cheat')} ({f['rule']})"[:255],
                    "message": str(f.get("detail") or f["rule"])[:64000]})
    return out


def from_sarif(log: dict) -> list[dict]:
    """Annotations read back from a SARIF log this module wrote (the App gets the log in the run's artifact)."""
    out = []
    for run in log.get("runs") or []:
        for r in run.get("results") or []:
            loc = ((r.get("locations") or [{}])[0].get("physicalLocation") or {})
            line = int((loc.get("region") or {}).get("startLine") or 1)
            out.append({"path": str((loc.get("artifactLocation") or {}).get("uri") or ".knos/gate.yml"), "start_line": line,
                        "end_line": line, "annotation_level": "failure", "title": f"Knos Gate: {r.get('ruleId', 'cheat')}"[:255],
                        "message": str((r.get("message") or {}).get("text") or "")[:64000]})
    return out[:MAX_ANNOTATIONS]


def workflow_commands(notes: list[dict]) -> str:
    """Action mode: the annotations as `::error file=...,line=...,title=...::message` lines. The Action's job is the
    check, so GitHub puts these on it, at those lines of the pull request's diff."""
    def esc(s: str, prop: bool = False) -> str:
        s = s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        return s.replace(":", "%3A").replace(",", "%2C") if prop else s
    return "".join(f"::error file={esc(a['path'], True)},line={a['start_line']},title={esc(a['title'], True)}::{esc(a['message'])}\n"
                   for a in notes)


def gzip64(log: dict) -> str:
    return base64.b64encode(gzip.compress(json.dumps(log, separators=(",", ":")).encode(), mtime=0)).decode()
