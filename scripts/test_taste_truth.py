"""test_taste_truth: for people who love a film, which other films do they love? Qloo against Claude alone, scored on
MovieLens 32M (F. Maxwell Harper and Joseph A. Konstan (2015), "The MovieLens Datasets: History and Context").

Seeds: 30 films, random.Random(3).sample of the films with at least 20,000 ratings, sorted by movieId first. Truth per
seed: fans rated it 4.5 or more; candidates are other films with at least 5,000 ratings, rated 4.5 or more by at least
300 fans; lift = (share of fans who rated it 4.5+) / (share of all users who rated it 4.5+); truth = top 10 by lift.
Claude alone: claude -p, web tools denied, 5 titles with years. Knos: GET /api/taste/movie on the live app (Knos's
own Qloo client: search type urn:entity:movie, first result of the same year, then insights take 20), the first 5
that map to MovieLens. Metric: overlap at 5 with the truth top 10, divided by 5, mean over 30; paired bootstrap,
2,000 resamples, random seed 3, 95% interval for Knos minus Claude. Plan: docs/reference/taste_truth_plan.md,
committed with its sha256 before any prediction. Run once.

    python scripts/test_taste_truth.py --truth <ml-32m folder> <world>/taste-truth.json
    python scripts/test_taste_truth.py --claude <world>/taste-truth.json <world>/taste-claude.json
    python scripts/test_taste_truth.py --knos <world>/taste-truth.json <world>/taste-knos.json
    python scripts/test_taste_truth.py --score <world>/taste-truth.json <world>/taste-claude.json <world>/taste-knos.json
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "reference" / "taste_truth_plan.md"
PUBLIC = ROOT / "docs" / "reference" / "taste_truth.json"
APP = "https://knos.onrender.com"
SEEDS, SEED_MIN, CAND_MIN, FAN_MIN, HIGH, TOP, K, BOOT, RSEED = 30, 20_000, 5_000, 300, 4.5, 10, 5, 2000, 3
PROMPT = ("Reply with exactly 5 lines and nothing else. Each line is one film title and its year in parentheses. The 5 films "
          "that people who love {title} are most likely to also love, excluding that film.")
CITE = 'F. Maxwell Harper and Joseph A. Konstan (2015), "The MovieLens Datasets: History and Context", ACM TiiS 5(4)'
ARTICLES = ("the", "a", "an")


def norm(title: str) -> str:
    """Lowercase, accents and punctuation out, one leading or trailing article out."""
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    w = t.split()
    if w and w[0] in ARTICLES:
        w = w[1:]
    elif w and w[-1] in ARTICLES:
        w = w[:-1]
    return " ".join(w)


def split_ml(title: str) -> tuple[list[str], int | None]:
    """A MovieLens title: its names (the main one and a parenthesised alternate) and its year."""
    m = re.match(r"^(.*?)\s*\((\d{4})\)\s*$", title.strip())
    if not m:
        return [title], None
    body, year = m[1], int(m[2])
    names = [re.sub(r"\s*\(.*?\)\s*", " ", body).strip()] + [x.strip() for x in re.findall(r"\(([^()]*)\)", body)]
    names = [re.sub(r"^a\.k\.a\.\s*", "", x, flags=re.I) for x in names if x]
    return names, year


def search_name(name: str) -> str:
    """'Matrix, The' -> 'The Matrix' (MovieLens puts the article last)."""
    m = re.match(r"^(.*), (The|A|An|L'|Le|La|Les|Il|El|Das|Die|Der)$", name)
    return f"{m[2]} {m[1]}".replace("L' ", "L'") if m else name


def line_key(line: str) -> tuple[str, int | None]:
    t = re.sub(r"^\s*(\d+[.)]|[-*\u2022])\s*", "", line).strip().strip("*").strip()
    m = re.match(r"^(.*?)\s*\((\d{4})\)", t)
    return (norm(m[1]), int(m[2])) if m else (norm(t), None)


def truth(folder: str, out: str) -> int:
    d = Path(folder)
    titles: dict[int, str] = {}
    with open(d / "movies.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            titles[int(r["movieId"])] = r["title"]
    n_r: dict[int, int] = defaultdict(int)
    n_hi: dict[int, int] = defaultdict(int)
    users = set()
    with open(d / "ratings.csv", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        for u, m, r, _t in rd:
            m = int(m)
            n_r[m] += 1
            if float(r) >= HIGH:
                n_hi[m] += 1
            users.add(u)
    pool = sorted(m for m, n in n_r.items() if n >= SEED_MIN)
    seeds = random.Random(RSEED).sample(pool, SEEDS)
    sset = set(seeds)
    fans: dict[int, int] = defaultdict(int)
    co: dict[int, dict[int, int]] = {s: defaultdict(int) for s in seeds}

    def flush(hi: list[int]):
        mine = [s for s in hi if s in sset]
        for s in mine:
            fans[s] += 1
            c = co[s]
            for m in hi:
                if m != s:
                    c[m] += 1
    with open(d / "ratings.csv", encoding="utf-8") as f:
        rd = csv.reader(f)
        next(rd)
        cur, hi = None, []
        for u, m, r, _t in rd:
            if u != cur:
                if hi:
                    flush(hi)
                cur, hi = u, []
            if float(r) >= HIGH:
                hi.append(int(m))
        if hi:
            flush(hi)
    nu = len(users)
    rows = []
    for s in seeds:
        cands = []
        for m, c in co[s].items():
            if n_r[m] >= CAND_MIN and c >= FAN_MIN and n_hi[m]:
                cands.append(((c / fans[s]) / (n_hi[m] / nu), m))
        cands.sort(key=lambda x: (-x[0], x[1]))
        rows.append({"seed": s, "title": titles[s], "fans": fans[s], "top10": [m for _, m in cands[:TOP]],
                     "top10_titles": [titles[m] for _, m in cands[:TOP]], "lift": [round(x, 3) for x, _ in cands[:TOP]]})
    index: dict[str, list[int]] = defaultdict(list)
    for m, t in titles.items():
        names, y = split_ml(t)
        for nm in names:
            index[f"{norm(nm)}|{y}"].append(m)
    doc = {"users": nu, "ratings": sum(n_r.values()), "seed_pool": len(pool), "seeds": rows, "index": index, "cite": CITE}
    Path(out).write_text(json.dumps(doc), encoding="utf-8")
    print(f"{nu} users, {doc['ratings']} ratings, {len(pool)} films with {SEED_MIN}+ ratings, 30 seeds: {[titles[s] for s in seeds[:5]]}...")
    return 0


def mapped(lines: list[str], index: dict, seed: int) -> tuple[list[int], list[str]]:
    got, missed = [], []
    for ln in lines:
        n, y = line_key(ln)
        ids = [m for m in index.get(f"{n}|{y}", []) if m != seed]
        if ids and ids[0] not in got:
            got.append(ids[0])
        elif not ids:
            missed.append(ln.strip())
    return got, missed


def claude_arm(truth_file: str, out: str) -> int:
    t = json.loads(Path(truth_file).read_text(encoding="utf-8"))
    exe = shutil.which("claude.exe") or shutil.which("claude.cmd") or shutil.which("claude")
    version = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    rows, models = [], set()
    with tempfile.TemporaryDirectory(prefix="knos-taste-") as cwd:
        for s in t["seeds"]:
            run = subprocess.run([exe, "-p", PROMPT.format(title=s["title"]), "--output-format", "json", "--strict-mcp-config",
                                  "--mcp-config", '{"mcpServers": {}}', "--disallowedTools", "WebFetch", "WebSearch"],
                                 cwd=cwd, capture_output=True, text=True, timeout=600)
            try:
                j = json.loads(run.stdout)
            except ValueError:
                j = {"result": ""}
            models |= set((j.get("modelUsage") or {}).keys())
            lines = [x for x in str(j.get("result") or "").splitlines() if x.strip()][:K]
            got, missed = mapped(lines, t["index"], s["seed"])
            rows.append({"seed": s["seed"], "said": lines, "top5": got, "unmapped": missed})
            print(s["title"], "->", len(got), "mapped", ("unmapped: " + "; ".join(missed)) if missed else "", flush=True)
    Path(out).write_text(json.dumps({"claude_code": version, "models": sorted(models), "rows": rows}, indent=1), encoding="utf-8")
    return 0


def knos_arm(truth_file: str, out: str) -> int:
    t = json.loads(Path(truth_file).read_text(encoding="utf-8"))
    rows = []
    for s in t["seeds"]:
        names, year = split_ml(s["title"])
        q = urllib.parse.urlencode({"title": search_name(names[0]), "year": year})
        with urllib.request.urlopen(urllib.request.Request(f"{APP}/api/taste/movie?{q}", headers={"User-Agent": "knos-test"}), timeout=180) as r:
            ans = json.loads(r.read())
        if not ans.get("resolved"):
            rows.append({"seed": s["seed"], "resolved": None, "top5": [], "unmapped": [], "note": "no search result of the same year: overlap 0"})
            print(s["title"], "-> not resolved", flush=True)
            continue
        lines = [f"{f['name']} ({f['year']})" for f in ans.get("films") or []]
        got, missed = [], []
        for ln in lines:
            g, mi = mapped([ln], t["index"], s["seed"])
            got += [x for x in g if x not in got]
            missed += mi
            if len(got) >= K:
                break
        rows.append({"seed": s["seed"], "resolved": ans["resolved"]["name"], "top5": got[:K], "unmapped": missed})
        print(s["title"], "->", ans["resolved"]["name"], len(got[:K]), "mapped", flush=True)
        time.sleep(0.5)
    Path(out).write_text(json.dumps({"rows": rows}, indent=1), encoding="utf-8")
    return 0


def score(truth_file: str, claude_file: str, knos_file: str) -> int:
    t = json.loads(Path(truth_file).read_text(encoding="utf-8"))
    ca = json.loads(Path(claude_file).read_text(encoding="utf-8"))
    kn = json.loads(Path(knos_file).read_text(encoding="utf-8"))
    top10 = {s["seed"]: set(s["top10"]) for s in t["seeds"]}
    a = {r["seed"]: len(set(r["top5"][:K]) & top10[r["seed"]]) / K for r in ca["rows"]}
    b = {r["seed"]: len(set(r["top5"][:K]) & top10[r["seed"]]) / K for r in kn["rows"]}
    seeds = [s["seed"] for s in t["seeds"]]
    n = len(seeds)
    ma, mb = sum(a[s] for s in seeds) / n, sum(b[s] for s in seeds) / n
    rng, diffs = random.Random(RSEED), []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in seeds]
        diffs.append(sum(b[seeds[i]] - a[seeds[i]] for i in idx) / n)
    diffs.sort()
    lo, hi = diffs[int(0.025 * BOOT)], diffs[int(0.975 * BOOT) - 1]
    sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
    reading = "Knos with Qloo is ahead" if lo > 0 else "Claude alone is ahead" if hi < 0 else "the test cannot tell them apart"
    titles = {s["seed"]: s["title"] for s in t["seeds"]}
    ml = {}
    for s in t["seeds"]:
        ml.update(dict(zip(s["top10"], s["top10_titles"])))
    doc = {"made": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "plan": "docs/reference/taste_truth_plan.md", "plan_sha256": sha,
           "n": n, "metric": "overlap at 5 with the MovieLens top 10 by lift, divided by 5", "data": CITE,
           "mean_overlap": {"claude_alone": round(ma, 4), "knos_with_qloo": round(mb, 4)}, "difference": round(mb - ma, 4),
           "bootstrap": {"resamples": BOOT, "seed": RSEED, "interval_95": [round(lo, 4), round(hi, 4)]}, "reading": reading,
           "claude": {"claude_code": ca.get("claude_code"), "models": ca.get("models")},
           "knos_resolved": sum(1 for r in kn["rows"] if r.get("resolved")),
           "per_seed": [{"seed": titles[s], "truth_top10": [ml.get(m, str(m)) for m in next(x["top10"] for x in t["seeds"] if x["seed"] == s)],
                         "claude": a[s], "knos": b[s]} for s in seeds]}
    PUBLIC.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    passed = lo > 0
    lines = [f"plan {doc['plan']} sha256 {sha}", f"claude: {doc['claude']}; Knos resolved {doc['knos_resolved']} of {n} seeds",
             f"n {n}; mean overlap at 5: Claude alone {ma:.3f}, Knos with Qloo {mb:.3f}; difference {mb - ma:+.3f}, "
             f"95% interval [{lo:+.3f}, {hi:+.3f}]; {reading}",
             f"{'PASS' if passed else 'FAIL'} test_taste_truth: run once on {n} films, overlap {ma:.3f} Claude alone vs {mb:.3f} Knos with Qloo, "
             f"difference {mb - ma:+.3f} [{lo:+.3f}, {hi:+.3f}], {reading}"]
    print("\n".join(lines))
    (Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world") / "test_taste_truth.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit({"--truth": truth, "--claude": claude_arm, "--knos": knos_arm, "--score": score}[args[0]](*args[1:]))
