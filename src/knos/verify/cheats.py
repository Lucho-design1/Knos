"""The cheat checks `knos verify` runs on a change before its tests: the referee's cheat library (knos.cheats) when this
install has it, else the minimal local rule set below. Neither runs any code of the change: they read its diff.

Local rules (each finding carries the referee's category names, so a receipt reads the same either way):

    test_edited         an existing test file is changed or deleted (adding a new test is allowed and noted)
    assertion_removed   a line holding an assertion is removed from a test file
    out_of_scope        a changed file is outside the scope the repository declares (.knos/gate.yml `scope`)
    workflow_edited     a CI workflow or Knos's own config (.github/workflows/**, .knos/**) is changed
    data_tampering      a fixture, golden file or snapshot is changed (fixtures/, testdata/, __snapshots__/, *.snap, *.golden)
    skip_added          a skip or focus marker is added in a test (pytest.skip, xfail, it.only, t.Skip, #[ignore], ...)
"""

from __future__ import annotations

import fnmatch
import re

_TEST = re.compile(r"(?:^|/)(?:tests?|__tests__|spec|specs)/|(?:^|/)test_[^/]+\.py$|_test\.(?:py|go|rs|rb|exs?)$|"
                   r"\.(?:test|spec)\.[cm]?[jt]sx?$|(?:^|/)conftest\.py$|Tests?\.(?:cs|java|kt|swift)$")
_DATA = re.compile(r"(?:^|/)(?:fixtures?|testdata|test_data|__snapshots__|golden|goldens|expected)/|\.(?:snap|golden)$")
_CONTROL = re.compile(r"^(?:\.github/workflows/|\.knos/|\.gitlab-ci\.yml$|\.circleci/|azure-pipelines\.yml$)")
_ASSERT = re.compile(r"\b(?:assert\w*|expect\s*\(|should\.|t\.(?:Error|Fatal)\w*|self\.assert\w*|XCTAssert\w*|require\.\w+)")
_SKIP = re.compile(r"(?:pytest\.(?:skip|mark\.(?:skip|xfail))|@unittest\.skip|\bxfail\b|\b(?:it|describe|test)\.(?:only|skip)\s*\(|"
                   r"\bx(?:it|describe)\s*\(|\bt\.Skip\w*\s*\(|#\[ignore\]|@Disabled\b|@Ignore\b|\.skip\s*\()")


def _match(path: str, globs) -> bool:
    return any(fnmatch.fnmatch(path, g) or (g.endswith("/**") and path.startswith(g[:-3] + "/")) for g in globs)


def parse_diff(diff: str) -> dict:
    """{path: {"status": "added"|"modified"|"deleted"|"renamed", "added": [lines], "removed": [lines]}} of a unified diff."""
    files: dict = {}
    cur: dict | None = None
    named = False                   # this file's section began with `diff --git`, which named it
    old = ""
    left = right = 0                # lines of the current hunk still to read, old side and new side
    hunk = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")

    def strip(p: str) -> str:
        return p[2:] if p[:2] in ("a/", "b/") else p
    for line in diff.splitlines():
        if left > 0 or right > 0:   # inside a hunk every line is content, whatever it starts with
            if cur is not None and line.startswith("+"):
                cur["added"].append(line[1:])
                right -= 1
            elif cur is not None and line.startswith("-"):
                cur["removed"].append(line[1:])
                left -= 1
            elif not line.startswith("\\"):
                left, right = left - 1, right - 1
            continue
        m = hunk.match(line)
        if m:
            left, right = int(m.group(1) or 1), int(m.group(2) or 1)
        elif line.startswith("diff --git "):
            g = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            cur, named, old = {"status": "modified", "added": [], "removed": []}, True, ""
            if g:
                files[g.group(2)] = cur
                if g.group(1) != g.group(2):
                    cur["status"], cur["from"] = "renamed", g.group(1)
        elif line.startswith("--- "):
            old = line[4:].split("\t")[0].strip()
        elif line.startswith("+++ "):
            new = line[4:].split("\t")[0].strip()
            if not named:           # a plain unified diff (no `diff --git` line): the file starts here
                cur = {"status": "added" if old == "/dev/null" else "deleted" if new == "/dev/null" else "modified", "added": [], "removed": []}
                files[strip(old) if new == "/dev/null" else strip(new)] = cur
            named, old = False, ""
        elif cur is not None and line.startswith("new file mode"):
            cur["status"] = "added"
        elif cur is not None and line.startswith("deleted file mode"):
            cur["status"] = "deleted"
    return files


def as_git_diff(diff: str) -> str:
    """A plain unified diff (`--- a/x` / `+++ b/x`, as a model writes one) with the `diff --git` line before each
    file that git itself would print, so every reader of git diffs (the referee's library too) sees each file."""
    lines, out = diff.splitlines(), []
    left = right = 0
    named = False
    hunk = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
    for i, line in enumerate(lines):
        if left > 0 or right > 0:
            if line.startswith("+"):
                right -= 1
            elif line.startswith("-"):
                left -= 1
            elif not line.startswith("\\"):
                left, right = left - 1, right - 1
            out.append(line)
            continue
        m = hunk.match(line)
        if m:
            left, right = int(m.group(1) or 1), int(m.group(2) or 1)
        elif line.startswith("diff --git "):
            named = True
        elif line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            if not named:
                old = line[4:].split("\t")[0].strip()
                new = lines[i + 1][4:].split("\t")[0].strip()
                a = old[2:] if old.startswith("a/") else (new[2:] if old == "/dev/null" and new.startswith("b/") else old)
                b = new[2:] if new.startswith("b/") else (a if new == "/dev/null" else new)
                out.append(f"diff --git a/{a} b/{b}")
                if old == "/dev/null":
                    out.append("new file mode 100644")
                elif new == "/dev/null":
                    out.append("deleted file mode 100644")
            named = False
        out.append(line)
    return "\n".join(out) + ("\n" if diff.endswith("\n") else "")


def local_scan(diff: str, scope=()) -> list[dict]:
    """The local rules on a unified diff: [{rule, category, path, detail, severity}] (severity "refuse" or "flag")."""
    out: list[dict] = []

    def add(rule: str, path: str, detail: str, severity: str = "refuse") -> None:
        out.append({"rule": rule, "category": rule, "path": path, "detail": detail, "severity": severity})
    for path, f in parse_diff(diff).items():
        if _TEST.search(path):
            if f["status"] in ("modified", "deleted", "renamed"):
                add("test_edited", path, f"an existing test file is {f['status']}")
            else:
                add("test_added", path, "a new test file: allowed, not counted as evidence", "flag")
            if any(_ASSERT.search(x) for x in f["removed"]):
                add("assertion_removed", path, "a line with an assertion is removed")
            if any(_SKIP.search(x) for x in f["added"]):
                add("skip_added", path, "a skip or focus marker is added")
        if _DATA.search(path) and f["status"] != "added":
            add("data_tampering", path, f"a fixture or expected-output file is {f['status']}")
        if _CONTROL.search(path):
            add("workflow_edited", path, "CI or Knos configuration is changed")
        if scope and not _match(path, scope):
            add("out_of_scope", path, "outside the scope the repository declares")
    return out


def scan(diff: str, base_dir=None, scope=()) -> tuple[list[dict], str]:
    """(findings, engine): the referee's cheat library when importable (engine "knos.cheats"), else the local rules
    (engine "local"). Every finding is a plain dict {rule, category, path, detail, severity}."""
    diff = as_git_diff(diff)
    try:
        from .. import cheats as library  # type: ignore[attr-defined]
        scan_diff = library.scan_diff
    except (ImportError, AttributeError):
        return local_scan(diff, scope), "local"
    found = scan_diff(diff, base_dir=base_dir, scope=tuple(scope))
    rows = []
    for f in found:
        get = f.get if isinstance(f, dict) else lambda k, d="", f=f: getattr(f, k, d)
        rows.append({"rule": str(get("rule", "")), "category": str(get("category", "")), "path": str(get("path", "")),
                     "detail": str(get("detail", ""))[:300], "severity": str(get("severity", "refuse"))})
    return rows, "knos.cheats"


def refused(findings: list[dict]) -> bool:
    return any(f["severity"] == "refuse" for f in findings)
