"""A small research repository to try `knos reproduce` on: SYNTHETIC data, a nearest-centroid classifier, one claim.

    python -m knos.repro.example FOLDER [--tamper]

The data generator draws two Gaussian classes from a seed (synthetic: no real data). train.py fits the class centroids
on the train split and writes the accuracy on the split it is given. `--tamper` writes the same repository with an
inflated number in results.json and knos.yml: Knos re-runs it, the claim misses, and the result is contested and
kept private. Standard library only; runs in a second on one CPU.
"""
from __future__ import annotations

import sys
from pathlib import Path

MAKE_DATA = '''"""SYNTHETIC data: two Gaussian classes in 4 dimensions, drawn from --seed. Writes train.csv, test.csv, heldout.csv."""
import argparse, os, random

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
rng = random.Random(a.seed)
os.makedirs(a.out, exist_ok=True)
for split, n in (("train", 400), ("test", 400), ("heldout", 400)):
    with open(os.path.join(a.out, split + ".csv"), "w") as f:
        for _ in range(n):
            y = rng.randrange(2)
            x = [rng.gauss(0.5 if y else -0.5, 1.0) for _ in range(4)]
            f.write(",".join(f"{v:.6f}" for v in x) + f",{y}\\n")
'''

TRAIN = '''"""Nearest-centroid classifier. Fits on train.csv, writes {"accuracy": ...} for --split to --out."""
import argparse, json, os, random

ap = argparse.ArgumentParser()
ap.add_argument("--split", required=True)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--data", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
random.seed(a.seed)

def rows(name):
    with open(os.path.join(a.data, name + ".csv")) as f:
        return [([float(v) for v in ln.split(",")[:-1]], int(ln.split(",")[-1])) for ln in f if ln.strip()]

train = rows("train")
cent = {}
for y in (0, 1):
    xs = [x for x, t in train if t == y]
    cent[y] = [sum(c) / len(xs) for c in zip(*xs)]

def guess(x):
    return min(cent, key=lambda y: sum((u - v) ** 2 for u, v in zip(x, cent[y])))

test = rows(a.split)
acc = sum(guess(x) == y for x, y in test) / len(test)
with open(a.out, "w") as f:
    json.dump({"accuracy": acc, "n": len(test)}, f)
'''

SPEC = """knos: 1
name: synthetic-centroid
description: SYNTHETIC data. A nearest-centroid classifier on two Gaussian classes.
entry: python train.py --split {{split}} --seed {{seed}} --data {{data}} --out {{out}}
data:
  generator: python make_data.py --seed {{data_seed}} --out {{data}}
  seed: 7
  protected: [results.json]
splits:
  public: test
  heldout: heldout
claims:
  - id: accuracy
    metric: accuracy
    expected: {expected}
    tolerance: 0.02
    heldout_tolerance: 0.07
    reported: {{file: results.json, key: accuracy}}
compute:
  max_seconds: 600
seed: 0
authors:
  - github: drexthealpha
"""

# What train.py gives on the public split with data seed 7 (measured by tests/test_repro_run.py, which holds it).
HONEST = 0.8325
TAMPERED = 0.97


def write(folder: Path | str, tamper: bool = False, python: str = "python") -> Path:
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    expected = TAMPERED if tamper else HONEST
    (root / "make_data.py").write_text(MAKE_DATA, encoding="utf-8", newline="\n")
    (root / "train.py").write_text(TRAIN, encoding="utf-8", newline="\n")
    exe = Path(python).as_posix() if python != "python" else python      # knos.yml commands are split like a POSIX shell: no backslashes
    if any(c.isspace() for c in exe):
        exe = "python"
    (root / "knos.yml").write_text(SPEC.format(expected=expected).replace("python ", exe + " "), encoding="utf-8", newline="\n")
    (root / "results.json").write_text('{"accuracy": %s}\n' % expected, encoding="utf-8")
    (root / "README.md").write_text("# synthetic-centroid\n\nSYNTHETIC data. Accuracy on the test split: %s (results.json).\n" % expected, encoding="utf-8")
    return root


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    print(write(args[0], tamper="--tamper" in args, python=sys.executable))
