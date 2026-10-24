"""test_qloo_lift_ranked: the ranked Kickstarter test, run as docs/reference/qloo_lift_ranked_plan.md fixes it.

    python -I scripts/test_qloo_lift_ranked.py --build <Kickstarter_*.json.gz> <ks-sample.json> <lift-sample.json>
    KNOS_ADMIN_KEY=... python scripts/test_qloo_lift_ranked.py --collect <lift-sample.json> <lift-features.json> [--part i/n]
    python scripts/test_qloo_lift_ranked.py --score <ks-sample.json> <ks-features.json> <lift-sample.json> <lift-features.json>

--build draws the 300 projects (seed 1) from the dump, none of them in the earlier sample. --collect asks the hosted
app for each project's open signals and demand check (the numbers only, cached: a row is asked once). --score fits the
earlier tuned test's two models on its 250 tune rows (deterministic) and scores the 300 with them: Spearman of each
score against pledged/goal, and a 2,000-resample paired bootstrap 95% interval for rho(open signals + Qloo) minus
rho(open signals). It writes test_qloo_lift_ranked.txt next to the lift sample and the summary (numbers, the plan's
sha256; no project text, no Qloo answer) to docs/reference/qloo_lift_ranked.json.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import math
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_kickstarter_truth as tk  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "reference" / "qloo_lift_ranked_plan.md"
PUBLIC = ROOT / "docs" / "reference" / "qloo_lift_ranked.json"
N, SEED, BOOT = 300, 1, 2000


def build(dump: str, old_sample: str, out: str) -> int:
    taken = {r["id"] for r in json.loads(Path(old_sample).read_text(encoding="utf-8"))["rows"]}
    seen, pool = set(), []
    with gzip.open(dump, "rt", encoding="utf-8") as f:
        for line in f:
            d = (json.loads(line) if line.strip() else {}).get("data") or {}
            pid = str(d.get("id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            if pid in taken or d.get("state") not in tk.KEEP or not d.get("launched_at") or not tk.FROM <= tk._when(d["launched_at"]) <= tk.TO:
                continue
            goal, pledged = float(d.get("goal") or 0), float(d.get("pledged") or 0)
            if goal <= 0 or not d.get("blurb"):
                continue
            c = d.get("category") or {}
            main = c.get("parent_name") or c.get("name") or "?"
            pool.append({"id": pid, "name": " ".join(str(d.get("name") or "").split()), "blurb": " ".join(str(d["blurb"]).split()),
                         "category": {"main": main, "sub": c.get("name") or main}, "state": d["state"],
                         "launched_at": tk._when(d["launched_at"]).isoformat(), "ratio": pledged / goal})
    pool.sort(key=lambda r: int(r["id"]) if r["id"].isdigit() else 0)
    rows = random.Random(SEED).sample(pool, N)
    Path(out).write_text(json.dumps({"meta": {"eligible": len(pool), "seed": SEED, "source": tk.SOURCE}, "rows": rows}, indent=1), encoding="utf-8")
    print(f"{len(pool)} eligible; {len(rows)} drawn (seed {SEED}) to {out}")
    return 0


def models(old_sample: str, old_feats: str):
    """The earlier tuned test's two models, fit again on its 250 tune rows: (name, score function) each."""
    rows, feats = json.loads(Path(old_sample).read_text(encoding="utf-8"))["rows"], json.loads(Path(old_feats).read_text(encoding="utf-8"))
    tune = [r for r in rows if r["split"] == "tune" and r["id"] in feats]
    base = sum(r["state"] == "successful" for r in tune) / len(tune)
    cat: dict[str, list[int]] = {}
    for r in tune:
        cat.setdefault(r["category"]["main"], []).append(int(r["state"] == "successful"))
    rate = {c: (sum(v) + 5 * base) / (len(v) + 5) for c, v in cat.items()}
    out = []
    for name, cols in (("open_signals", tk.OPEN_F), ("open_signals_qloo", tk.OPEN_F + tk.QLOO_F)):
        def vec(f, row, cols=cols):
            return [f.get(c, 0.0) for c in cols] + [rate.get(row["category"]["main"], base)]
        xt = [vec(feats[r["id"]], r) for r in tune]
        mu = [sum(c) / len(c) for c in zip(*xt)]
        sd = [max(1e-9, (sum((v - m) ** 2 for v in c) / len(c)) ** 0.5) for c, m in zip(zip(*xt), mu)]
        w = tk._fit([[(a - m) / s for a, m, s in zip(v, mu, sd)] for v in xt], [int(r["state"] == "successful") for r in tune])

        def score(f, row, w=w, vec=vec, mu=mu, sd=sd):
            z = w[-1] + sum(b * (a - m) / s for a, m, s, b in zip(vec(f, row), mu, sd, w))
            return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
        out.append((name, score))
    return out


def ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1                    # ties take their average rank
        i = j + 1
    return r


def spearman(x: list[float], y: list[float]) -> float:
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def score_all(old_sample: str, old_feats: str, lift_sample: str, lift_feats: str) -> int:
    plan_sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
    rows = json.loads(Path(lift_sample).read_text(encoding="utf-8"))["rows"]
    feats = json.loads(Path(lift_feats).read_text(encoding="utf-8"))
    have = [r for r in rows if r["id"] in feats]
    (na, fa), (nb, fb) = models(old_sample, old_feats)
    y = [r["ratio"] for r in have]
    a = [fa(feats[r["id"]], r) for r in have]
    b = [fb(feats[r["id"]], r) for r in have]
    ra, rb = spearman(a, y), spearman(b, y)
    rng, diffs = random.Random(SEED), []
    for _ in range(BOOT):
        idx = [rng.randrange(len(have)) for _ in have]
        yy = [y[i] for i in idx]
        diffs.append(spearman([b[i] for i in idx], yy) - spearman([a[i] for i in idx], yy))
    diffs.sort()
    lo, hi = diffs[int(0.025 * BOOT)], diffs[int(0.975 * BOOT) - 1]
    reading = "Qloo helps" if lo > 0 else "Qloo hurts" if hi < 0 else "the test cannot tell"
    full = len(have) == N
    doc = {"made": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "plan": str(PLAN.relative_to(ROOT)).replace("\\", "/"),
           "plan_sha256": plan_sha, "projects": len(have), "outcome": "pledged / goal",
           "spearman": {na: round(ra, 4), nb: round(rb, 4)}, "difference": round(rb - ra, 4),
           "bootstrap": {"resamples": BOOT, "seed": SEED, "interval_95": [round(lo, 4), round(hi, 4)]}, "reading": reading, "source": tk.SOURCE}
    if full:
        PUBLIC.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    lines = [f"plan {doc['plan']} sha256 {plan_sha}", f"{len(have)} of {N} projects scored; outcome pledged/goal",
             f"Spearman: open signals {ra:.4f}, open signals + Qloo {rb:.4f}; difference {rb - ra:+.4f}, 95% interval [{lo:+.4f}, {hi:+.4f}] ({BOOT} resamples): {reading}",
             ("PASS" if full else "FAIL") + f" test_qloo_lift_ranked: run once on {len(have)} projects, rho {ra:.3f} vs {rb:.3f}, "
             f"difference {rb - ra:+.3f} [{lo:+.3f}, {hi:+.3f}], {reading}"]
    print("\n".join(lines))
    (Path(lift_sample).parent / "test_qloo_lift_ranked.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if full else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--build"]:
        sys.exit(build(a[1], a[2], a[3]))
    if a[:1] == ["--collect"]:
        sys.exit(tk.collect(a[1], a[2], tuple(int(x) for x in a[a.index("--part") + 1].split("/")) if "--part" in a else None))  # type: ignore[arg-type]
    if a[:1] == ["--score"]:
        sys.exit(score_all(a[1], a[2], a[3], a[4]))
    print(__doc__)
    sys.exit(2)
