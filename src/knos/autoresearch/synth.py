"""SYNTHETIC data for the autoresearch example: binary labels from a known nonlinear rule plus noise.

Every row is generated here from a seed; none of it describes anything real. Six features x0..x5 drawn N(0,1);
y = 1 when x0^2 + x1^2 - 1.4 + 0.8*x2*x3 + noise > 0 (noise N(0, 0.3)); x4 and x5 are pure noise. A linear model
cannot see the rule; squared and pairwise features can. Standard library only.
"""
from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path

FEATURES = 6
HEADER = [f"x{i}" for i in range(FEATURES)]


def rows(seed: str | int, n: int) -> list[tuple[list[float], int]]:
    rng = random.Random(f"knos-autoresearch:{seed}")
    out = []
    for _ in range(n):
        x = [round(rng.gauss(0.0, 1.0), 6) for _ in range(FEATURES)]
        s = x[0] * x[0] + x[1] * x[1] - 1.4 + 0.8 * x[2] * x[3] + rng.gauss(0.0, 0.3)
        out.append((x, 1 if s > 0 else 0))
    return out


def write(path: Path, data: list[tuple[list[float], int]], labels: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER + (["y"] if labels else []))
        for x, y in data:
            w.writerow([repr(v) for v in x] + ([y] if labels else []))
    return path


def digest(data: list[tuple[list[float], int]]) -> str:
    h = hashlib.sha256()
    for x, y in data:
        h.update((",".join(repr(v) for v in x) + f";{y}\n").encode())
    return h.hexdigest()
