"""Knos's cheat library: named, tested rules for every way of passing a check without doing the work.

    from knos import cheats
    cheats.scan(base, pr)              # two trees; runs none of the pull request's code
    cheats.scan_diff(diff_text, base_dir=base)
    cheats.scan_outcome(funded, now)   # a measured outcome's committed inputs
    cheats.refused(findings)           # any finding with severity "refuse"
    cheats.CASES                       # the 63 tamper-benchmark cases, each with the rule that refuses it
    cheats.red_team()                  # how many known cases a scanner catches (the gate on any referee change)

docs/reference/REFEREE.md describes every rule.
"""

from __future__ import annotations

from . import rules as _rules  # noqa: F401 - registers the change rules
from .library import (CATEGORIES, RULES, Change, FileChange, Finding, Rule, add_rule, categories, change_from_diff,
                      change_from_trees, matches, parse_diff, refused, rules, run, scan, scan_diff)
from .outcome import scan_outcome
from .tamper63 import JUDGED_END_TO_END, Case, _build

CASES = _build()


def cases(language: str | None = None, category: str | None = None) -> list[Case]:
    return [c for c in CASES if (language is None or c.language == language) and (category is None or c.category == category)]


def bench_root():
    """tests/bench_tamper of a source checkout, or None for an installed package (the cases need the samples)."""
    from pathlib import Path
    here = Path(__file__).resolve().parents[3] / "tests" / "bench_tamper"
    return here if here.is_dir() else None


def build_case(case: Case, base, pr) -> None:
    """Lay out one case: the sample's base at `base` and the cheating pull request at `pr`. Needs a source checkout."""
    import importlib.util
    import shutil
    from pathlib import Path
    root = bench_root()
    if root is None:
        raise ValueError("the tamper cases need tests/bench_tamper from a source checkout of Knos")
    ignore = shutil.ignore_patterns("__pycache__", "node_modules")
    shutil.copytree(root / case.sample, base, ignore=ignore)
    shutil.copytree(root / case.sample, pr, ignore=ignore)
    spec = importlib.util.spec_from_file_location(f"knos_cheat_{case.bench[0][:-3]}", root / case.bench[0])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    getattr(mod, case.bench[1])(Path(pr))


def red_team(scan_fn=None) -> dict:
    """Every known case through a scanner (default: this library's `scan`): {"caught", "total", "missed"}. A change
    to the referee must catch at least as many as the referee it replaces, and none it caught before may be missed."""
    import tempfile
    from pathlib import Path
    scan_fn = scan_fn or (lambda base, pr: scan(base, pr))
    missed = []
    with tempfile.TemporaryDirectory(prefix="knos-red-team-") as t:
        for c in CASES:
            base, pr = Path(t) / c.id / "base", Path(t) / c.id / "pr"
            build_case(c, base, pr)
            if not refused(scan_fn(base, pr)):
                missed.append(c.id)
    return {"caught": len(CASES) - len(missed), "total": len(CASES), "missed": missed}


__all__ = ["CATEGORIES", "CASES", "Case", "Change", "FileChange", "Finding", "JUDGED_END_TO_END", "RULES", "Rule",
           "add_rule", "build_case", "cases", "categories", "change_from_diff", "change_from_trees", "matches",
           "parse_diff", "red_team", "refused", "rules", "run", "scan", "scan_diff", "scan_outcome"]
