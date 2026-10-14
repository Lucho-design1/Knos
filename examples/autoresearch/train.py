"""The ONE file agents edit (examples/autoresearch). A small classifier on SYNTHETIC data, standard library only, CPU.

The referee runs it as:
    python -I train.py --train train.csv --val val.csv --predict predict.csv --out preds.json --seed S --budget T
It must stop training before T seconds, write {"predictions": [0|1, ...]} for predict.csv's rows to --out, and may
print one JSON line with its own validation score (shown to the agent; the referee scores on sealed data itself).
"""
import argparse
import csv
import json
import math
import random
import time

CONFIG = {
    'features': 'linear',
    'standardize': False,
    'lr': 0.05,
    'epochs': 10,
    'l2': 0.0,
    'batch': 32,
}


def read(path):
    with open(path, newline="") as f:
        r = csv.reader(f)
        head = next(r)
        labelled = head[-1] == "y"
        X, y = [], []
        for row in r:
            vals = [float(v) for v in (row[:-1] if labelled else row)]
            X.append(vals)
            y.append(int(row[-1]) if labelled else 0)
    return X, y


def featurize(x, kind):
    out = list(x)
    if kind in ("square", "square+pairs"):
        out += [v * v for v in x]
    if kind == "square+pairs":
        out += [x[i] * x[j] for i in range(len(x)) for j in range(i + 1, len(x))]
    return out


def fit(X, y, cfg, seed, deadline):
    rng = random.Random(seed)
    F = [featurize(x, cfg["features"]) for x in X]
    d = len(F[0])
    mu, sd = [0.0] * d, [1.0] * d
    if cfg["standardize"]:
        mu = [sum(r[j] for r in F) / len(F) for j in range(d)]
        sd = [math.sqrt(sum((r[j] - mu[j]) ** 2 for r in F) / len(F)) or 1.0 for j in range(d)]
    F = [[(r[j] - mu[j]) / sd[j] for j in range(d)] for r in F]
    w, b = [rng.gauss(0.0, 0.01) for _ in range(d)], 0.0
    idx = list(range(len(F)))
    for _epoch in range(cfg["epochs"]):
        rng.shuffle(idx)
        for s in range(0, len(idx), cfg["batch"]):
            if time.monotonic() > deadline:
                return w, b, mu, sd
            batch = idx[s:s + cfg["batch"]]
            gw, gb = [0.0] * d, 0.0
            for i in batch:
                z = b + sum(wj * fj for wj, fj in zip(w, F[i]))
                p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
                e = p - y[i]
                gb += e
                for j in range(d):
                    gw[j] += e * F[i][j]
            n = len(batch)
            w = [wj - cfg["lr"] * (g / n + cfg["l2"] * wj) for wj, g in zip(w, gw)]
            b -= cfg["lr"] * gb / n
    return w, b, mu, sd


def predict(model, X, cfg):
    w, b, mu, sd = model
    out = []
    for x in X:
        f = featurize(x, cfg["features"])
        z = b + sum(wj * (fj - m) / s for wj, fj, m, s in zip(w, f, mu, sd))
        out.append(1 if z > 0 else 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    for a in ("--train", "--val", "--predict", "--out"):
        ap.add_argument(a, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=float, default=20.0)
    a = ap.parse_args()
    deadline = time.monotonic() + a.budget * 0.8
    X, y = read(a.train)
    model = fit(X, y, CONFIG, a.seed, deadline)
    Xv, yv = read(a.val)
    val = sum(int(p == t) for p, t in zip(predict(model, Xv, CONFIG), yv)) / len(yv)
    Xp, _ = read(a.predict)
    with open(a.out, "w") as f:
        json.dump({"predictions": predict(model, Xp, CONFIG)}, f)
    print(json.dumps({"val_accuracy": round(val, 6)}))


if __name__ == "__main__":
    main()
