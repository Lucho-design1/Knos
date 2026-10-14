"""Run one candidate file the way the referee does: in a fresh directory that holds only the candidate, the public
data and the hidden rows' FEATURES (never their labels), with an almost empty environment, Python's isolated mode and
a hard wall-clock limit (the task's time budget plus a grace for start-up).

    python -I <editable> --train train.csv --val val.csv --predict predict.csv --out preds.json --seed S --budget T

The candidate writes {"predictions": [0|1, ...]} to preds.json (one per predict.csv row) and may print one JSON line
with its own validation score; the referee never uses that line to decide, it is shown to the agent.

This is a process boundary, not a security sandbox: the static rules in judge.py (an import allowlist, no reaching
for sealed paths) run first, and the labels are simply not on disk. A hosted referee runs this on its own runner.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import synth

GRACE_S = 5.0


@dataclass
class RunResult:
    ok: bool
    predictions: list[int] = field(default_factory=list)
    reported: dict = field(default_factory=dict)
    wall_s: float = 0.0
    error: str = ""
    timed_out: bool = False


def _env() -> dict[str, str]:
    env = {"PATH": os.defpath, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    for k in ("SYSTEMROOT", "TEMP", "TMP"):       # Windows cannot start Python without SYSTEMROOT
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def run(source: str, editable: str, public: dict[str, list], predict: list, seed: int, budget_s: float,
        python: str | None = None) -> RunResult:
    with tempfile.TemporaryDirectory(prefix="knos-ar-") as d:
        box = Path(d)
        (box / editable).write_text(source, encoding="utf-8")
        synth.write(box / "train.csv", public["train"])
        synth.write(box / "val.csv", public["val"])
        synth.write(box / "predict.csv", predict, labels=False)
        cmd = [python or sys.executable, "-I", editable, "--train", "train.csv", "--val", "val.csv",
               "--predict", "predict.csv", "--out", "preds.json", "--seed", str(seed), "--budget", str(budget_s)]
        t0 = time.monotonic()
        try:
            p = subprocess.run(cmd, cwd=box, env=_env(), capture_output=True, text=True, timeout=budget_s + GRACE_S)
        except subprocess.TimeoutExpired:
            return RunResult(False, wall_s=time.monotonic() - t0, error=f"over the time budget ({budget_s:g} s)", timed_out=True)
        wall = time.monotonic() - t0
        if p.returncode != 0:
            tail = (p.stderr or p.stdout).strip().splitlines()[-1:] or ["no output"]
            return RunResult(False, wall_s=wall, error=f"exit {p.returncode}: {tail[0][:200]}")
        reported = {}
        for line in reversed(p.stdout.strip().splitlines()):
            try:
                got = json.loads(line)
            except ValueError:
                continue
            if isinstance(got, dict):
                reported = {k: v for k, v in got.items() if isinstance(v, (int, float))}
                break
        try:
            preds = json.loads((box / "preds.json").read_text(encoding="utf-8"))["predictions"]
        except (OSError, ValueError, KeyError, TypeError):
            return RunResult(False, reported=reported, wall_s=wall, error="no readable preds.json")
        if not isinstance(preds, list) or len(preds) != len(predict) or any(v not in (0, 1) or isinstance(v, bool) for v in preds):
            return RunResult(False, reported=reported, wall_s=wall,
                             error=f"preds.json must list {len(predict)} predictions, each 0 or 1")
        return RunResult(True, predictions=[int(v) for v in preds], reported=reported, wall_s=wall)
