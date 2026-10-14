"""The self loop's merge rules, beside the cheat library (knos.cheats), all read without running the candidate:

    self.core_path          a trusted-core path changed (config.agent_findings)            refuse
    self.outside_product    a path that is not product changed                              refuse
    self.test_count_dropped fewer test functions in the files the change touched            refuse
    self.asserts_dropped    fewer assert statements in the tests the change touched         refuse
    self.logging_removed    logging calls removed from source and not put back              refuse
    self.claim_not_reproduced  the number the agent reported is not what the referee measured   refuse
    self.implausible_gain   a gain above the target's implausible_gain_rel                  held for the founder

The cheat library already refuses deleted tests, removed assertions in edited tests and removed detector markers
(test_deleted, assertion_removed, detector_marker_removed); these rules count what a change could spread across
files. A cheat caught here that the library does not know is reported with `proposed_rule`, so the founder can add it
to knos.cheats (the library is core: the loop never edits it).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .. import cheats as _cheats

LOGGING = re.compile(r"(\b(log|logger|logging|LOG|_log)\.(debug|info|warning|warn|error|exception|critical|log)\(|"
                     r"\bprint\([^#]*file\s*=\s*sys\.stderr|\bsys\.stderr\.write\()")


def _tests_in(text: str | None) -> tuple[int, int]:
    """(test functions, assert statements) of a Python test file's text; (0, 0) when it does not parse."""
    if not text:
        return 0, 0
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 0, 0
    tests = asserts = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            tests += 1
        elif isinstance(node, ast.Assert):
            asserts += 1
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.startswith("assert"):
            asserts += 1
    return tests, asserts


def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.endswith(".py") and (path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py"))


def counts(parent_dir, candidate_dir, paths) -> dict:
    """Test functions and asserts in the changed test files, before and after."""
    before, after = [0, 0], [0, 0]
    for rel in paths:
        if not is_test_file(rel):
            continue
        b = _tests_in(_read(Path(parent_dir) / rel))
        a = _tests_in(_read(Path(candidate_dir) / rel))
        before = [before[0] + b[0], before[1] + b[1]]
        after = [after[0] + a[0], after[1] + a[1]]
    return {"tests_before": before[0], "tests_after": after[0], "asserts_before": before[1], "asserts_after": after[1]}


def static_findings(diff_text: str, parent_dir, candidate_dir) -> tuple[list, dict]:
    """The rules above that read the trees and the diff. Returns (findings, counts)."""
    files = _cheats.parse_diff(diff_text)
    paths = sorted({f.path for f in files})
    c = counts(parent_dir, candidate_dir, paths)
    out = []
    if c["tests_after"] < c["tests_before"]:
        out.append(_cheats.Finding("self.test_count_dropped", "test_edited", "",
                                   f"test functions in the changed files: {c['tests_before']} -> {c['tests_after']}"))
    if c["asserts_after"] < c["asserts_before"]:
        out.append(_cheats.Finding("self.asserts_dropped", "assertion_removed", "",
                                   f"assert statements in the changed test files: {c['asserts_before']} -> {c['asserts_after']}"))
    for f in files:
        if not f.path.endswith(".py") or is_test_file(f.path):
            continue
        gone = sum(bool(LOGGING.search(ln)) for ln in f.removed)
        came = sum(bool(LOGGING.search(ln)) for ln in f.added)
        if gone > came:
            out.append(_cheats.Finding("self.logging_removed", "assertion_removed", f.path,
                                       f"{gone - came} logging call(s) removed"))
    return out, c


def claim_findings(claimed, measured, tolerance_abs: float = 0.0) -> list:
    """The agent said its candidate scores `claimed`; the referee measured `measured`. Never trust the report."""
    if claimed is None:
        return []
    if measured is None or abs(float(claimed) - float(measured)) > float(tolerance_abs):
        return [_cheats.Finding("self.claim_not_reproduced", "rerun_mismatch", "",
                                f"the agent reported {claimed}; the referee measured {measured}")]
    return []


def gain(parent_metric, candidate_metric, direction: str) -> float | None:
    if parent_metric is None or candidate_metric is None:
        return None
    return float(parent_metric) - float(candidate_metric) if direction == "lower" else float(candidate_metric) - float(parent_metric)


def implausible(parent_metric, g, rel_limit) -> bool:
    """Fails closed: no limit set, or a gain on a parent metric of 0, is held for the founder."""
    if g is None or g <= 0:
        return False
    if rel_limit is None or parent_metric is None or float(parent_metric) == 0:
        return True
    return g / abs(float(parent_metric)) > float(rel_limit)


def library_rules() -> set[str]:
    return set(_cheats.RULES)


def proposed_rules(findings) -> list[str]:
    """Rules that fired here and are not in the cheat library yet: what the founder may add with cheats.add_rule."""
    have = library_rules()
    return sorted({f.rule for f in findings if f.rule.startswith("self.") and f.rule[5:] not in have})
