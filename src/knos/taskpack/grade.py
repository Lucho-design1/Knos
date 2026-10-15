"""Grade a candidate patch against a sealed task package: the cheat rules first (no code of the candidate runs when one
fires), then the hidden tests at the base commit with the patch applied. The output names counts and rules only: never
a hidden test's content or name.

Reward (knos.referee.reward's scale): 1.0 every hidden test passes and no cheat rule fires; 0.0 a test fails or the
patch does not apply; -1.0 a cheat rule fires. When the referee's cheat library (knos.cheats) is installed its scan of
the diff runs too, and any finding it refuses counts as a cheat. A patch git cannot read is refused (patch_unreadable).

LIMIT: the hidden tests run the candidate's code on this machine with a cleaned environment, not in a sandbox. Grade
untrusted patches inside a disposable container or VM.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from . import export as ex

_DIFF_PATH = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.M)
_PLUS = re.compile(r"^\+\+\+ (?:b/)?(\S+)$", re.M)


def touched(patch: str) -> list[str] | None:
    """Every path the patch touches, as git itself reads it (`git apply --numstat -z`, which also reads headers without a
    `diff --git` line), plus any path the headers name. None when git cannot read the patch: it is then refused."""
    with tempfile.TemporaryDirectory(prefix="knos-touched-") as tmp:
        f = Path(tmp) / "c.patch"
        f.write_bytes(patch.encode("utf-8"))      # the patch's own bytes: write_text would end its lines with CRLF on Windows
        got = subprocess.run(["git", "apply", "--numstat", "-z", str(f)], cwd=tmp, capture_output=True, timeout=60)
    if got.returncode != 0:
        return None
    paths: set[str] = set()
    parts = got.stdout.decode("utf-8", "replace").split("\x00")
    i = 0
    while i < len(parts):
        rec = parts[i]
        if not rec:
            i += 1
            continue
        fields = rec.split("\t")
        if len(fields) == 3 and fields[2]:
            paths.add(fields[2])
            i += 1
        else:                                   # a rename or copy: "add\tdel\t" then the old and the new path
            paths |= {x for x in parts[i + 1:i + 3] if x}
            i += 3
    if not paths:
        return None
    for a, b in _DIFF_PATH.findall(patch):
        paths |= {a, b}
    for p in _PLUS.findall(patch):
        if p != "/dev/null":
            paths.add(p)
    return sorted(paths)


def cheat_findings(patch: str, manifest: dict) -> list[dict]:
    """The package's own rules, then the referee's cheat library when it is installed."""
    scope = manifest["scope"]["allowed"]
    out: list[dict] = []
    paths = touched(patch)
    if paths is None:
        return [{"rule": "patch_unreadable", "path": ""}]
    for p in paths:
        if p.startswith(ex.PROTECTED_DIRS):
            out.append({"rule": "workflow_edited", "path": p})
        elif ex.is_test(p):
            out.append({"rule": "test_edited", "path": p})
        elif not ex.in_scope(p, scope):
            out.append({"rule": "out_of_scope", "path": p})
    try:
        from .. import cheats  # type: ignore[attr-defined]
    except ImportError:
        return out
    try:
        found = cheats.scan_diff(patch)      # scope is the package's own rule above ("" = top-level files)
        if cheats.refused(found):
            seen = {(f["rule"], f["path"]) for f in out}
            for f in found:
                if getattr(f, "severity", "refuse") == "refuse" and (f.category, f.path) not in seen:
                    out.append({"rule": f.category, "path": f.path, "by": "knos.cheats"})
    except Exception:  # noqa: BLE001 - the library's own failure is not the candidate's cheat
        pass
    return out


def grade(pack: Path | str, repo: Path | str, patch: str, *, key: bytes | None = None, run=subprocess.run) -> dict:
    """{reward, passed, cheats, tests: {count, summary}, task_id}. `repo`: a clone holding the package's base commit."""
    pack = Path(pack)
    wrong = ex.verify(pack, key)
    if wrong:
        raise ex.Refused("the package does not check: " + "; ".join(wrong))
    m = ex.load(pack)
    out = {"task_id": m["task_id"], "reward": 0.0, "passed": False, "cheats": [], "tests": {"count": m["sealed"]["tests_count"], "summary": ""}}
    if not patch.strip():
        out["cheats"] = [{"rule": "no_change", "path": ""}]
        out["reward"] = -1.0
        return out
    found = cheat_findings(patch, m)
    if found:
        out.update(cheats=found, reward=-1.0)
        return out
    hidden = ex.untar(ex.sealed(pack, "tests.tar", key))
    with tempfile.TemporaryDirectory(prefix="knos-grade-") as tmp:
        where = Path(tmp) / "work"
        ex.tree(Path(repo), m["source"]["base_commit"], where)
        (Path(tmp) / "candidate.patch").write_bytes(patch.encode("utf-8"))     # as written: no CRLF on Windows
        got = subprocess.run(["git", "apply", "--whitespace=nowarn", str(Path(tmp) / "candidate.patch")], cwd=str(where), capture_output=True, text=True, timeout=60)
        if got.returncode != 0:
            out["cheats"] = []
            out["tests"]["summary"] = "the patch does not apply at the base commit"
            return out
        for p, blob in hidden.items():
            (where / p).parent.mkdir(parents=True, exist_ok=True)
            (where / p).write_bytes(blob)
        res = ex.run_judge(where, m["judge"]["command"], sorted(hidden), float(m["judge"]["timeout_seconds"]), run)
    out["tests"]["summary"] = res["summary"]
    out["passed"] = bool(res["passed"])
    out["reward"] = 1.0 if res["passed"] else 0.0
    return out
