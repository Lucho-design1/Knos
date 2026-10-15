"""Test helpers for the Knos game: a fast stand-in for the referee's dynamic half (the static cheat rules are the real
ones), so the game's rules can be tested in milliseconds. One test (test_game_engine.py) plays with the real judge."""
from __future__ import annotations

import re
from pathlib import Path

from knos.autoresearch.judge import Verdict, judge_hash, static_findings

TASK = Path(__file__).resolve().parents[1] / "examples" / "autoresearch"


class FakeJudge:
    """Scores a file by its `# score: X dev Y final` comment; the real static rules refuse cheats first."""

    backend = "tests.FakeJudge"

    def __init__(self, task):
        self.task = task
        self.sealed_judge = judge_hash()

    def seal(self) -> dict:
        return {"spec_hash": self.task.spec_hash(self.sealed_judge), "judge_hash": self.sealed_judge, "editable": self.task.editable,
                "seeds": [1, 2], "tolerance": {"abs": 0.03}, "sealed_at": 0, "backend": self.backend}

    def judge(self, files, current, stage="dev"):
        found = static_findings(files, self.task.editable, current)
        if any(f.severity == "refuse" for f in found):
            return Verdict(False, reasons=[f"refused: {f.rule} {f.detail}" for f in found if f.severity == "refuse"], cheats=found)
        src = files[self.task.editable]
        if "crash" in src:
            return Verdict(False, scores=[], reasons=["seed 1: the run failed: Traceback ... sealed row 17"], cheats=found)
        m = re.search(r"# score: ([0-9.]+) final ([0-9.]+)", src)
        dev, fin = (float(m.group(1)), float(m.group(2))) if m else (0.5, 0.5)
        s = dev if stage == "dev" else fin
        return Verdict(True, score=s, scores=[s, s], cheats=found, reported={"val_accuracy": round(s - 0.01, 4)})


def attempt(base: str, dev: float, final: float, tag: str = "") -> str:
    """The baseline with a scoring comment (and a harmless CONFIG change so it is not the baseline)."""
    return base.replace("CONFIG = {", f"# score: {dev} final {final}\n# {tag}\nCONFIG = {{", 1)
