"""test_where_truth: where are 30 kinds of business most common per person, against the Census.

Truth: County Business Patterns 2023 for metro areas (cbp23msa.zip: columns msa, naics, est) over Vintage 2023 population
(cbsa-est2023-alldata.csv: CBSA, LSAD, POPESTIMATE2023), establishments per 100,000 people, top 10 per code, among the
Metropolitan Statistical Areas of at least 500,000 people (the candidates; both arms choose only from them).
(a) Claude alone: claude -p with the prompt of the plan, 5 metro names, each matched to a candidate CBSA by exact or
fuzzy name. (b) Knos: the official NAICS title through the live demand check (POST /api/check); its heatmap metros
(apps/wanted metros.py: TIGER/Line 2023 boundaries) among the candidates, those with at least 3 cells by mean affinity,
filled by those with 1 or 2 cells; no cells is overlap 0. Metric: overlap at 5 with the truth top 10, divided by 5, mean
over the codes; paired bootstrap, 2,000 resamples (seed 1), 95% percentile interval for (b) minus (a).
The plan is docs/reference/where_truth_plan.md, committed with its sha256 before any prediction. Run once.

    python scripts/test_where_truth.py --truth <census folder> <world>/where-truth.json
    python scripts/test_where_truth.py --claude <world>/where-truth.json <world>/where-claude.json
    python scripts/test_where_truth.py --knos <world>/where-truth.json <world>/where-knos.json
    python scripts/test_where_truth.py --score <world>/where-truth.json <world>/where-claude.json <world>/where-knos.json
"""
from __future__ import annotations

import csv
import datetime as dt
import difflib
import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "reference" / "where_truth_plan.md"
PUBLIC = ROOT / "docs" / "reference" / "where_truth.json"
APP = "https://knos.onrender.com"
CODES = ("713940 312120 722515 722511 722513 722410 812111 812112 812113 812910 541940 713110 713120 713910 713950 "
         "711130 711110 512131 611610 611620 621310 812199 811192 721110 721191 312130 312140 311811 624410 712110").split()
PROMPT = ("From US metropolitan areas with at least 500,000 people, list the 5 where {title} businesses are most common per "
          "person. Reply with 5 metro area names, one per line, nothing else.")
MIN_POP, TOP, K, BOOT, SEED = 500_000, 10, 5, 2000, 1
NO_MCP = '{"mcpServers": {}}'


def truth(folder: str, out: str) -> int:
    d = Path(folder)
    pop, names = {}, {}
    with open(d / "cbsa-est2023-alldata.csv", encoding="latin-1") as f:
        for r in csv.DictReader(f):
            if r["LSAD"] == "Metropolitan Statistical Area" and int(r["POPESTIMATE2023"]) >= MIN_POP:
                pop[r["CBSA"]] = int(r["POPESTIMATE2023"])
                names[r["CBSA"]] = r["NAME"]
    with open(d / "naics2017.txt", encoding="latin-1") as f:
        titles = {row[0].strip(): row[1].strip() for row in csv.reader(f) if row}
    est: dict[str, dict[str, int]] = {c: {} for c in CODES}
    with zipfile.ZipFile(d / "cbp23msa.zip") as z:
        for row in csv.DictReader(io.TextIOWrapper(z.open("cbp23msa.txt"), encoding="latin-1")):
            if row["naics"] in est and row["msa"] in pop:
                est[row["naics"]][row["msa"]] = int(row["est"])
    rows, dropped = [], []
    for c in CODES:
        if not est[c]:
            dropped.append(c)
            continue
        rate = sorted(((v / pop[m] * 100_000, m) for m, v in est[c].items()), key=lambda x: (-x[0], x[1]))
        rows.append({"naics": c, "title": titles[c], "top10": [m for _, m in rate[:TOP]], "rates": [round(r, 3) for r, _ in rate[:TOP]]})
    no_cbp = sorted(m for m in pop if not any(m in est[c] for c in CODES))
    doc = {"columns": {"cbp": ["msa", "naics", "est"], "population": ["CBSA", "LSAD", "POPESTIMATE2023", "NAME"]},
           "titles": "naics2017.txt (CBP reference naics-descriptions; the newest it publishes)",
           "candidates": [{"cbsa": m, "name": names[m], "pop": pop[m]} for m in sorted(pop)], "codes": rows, "dropped": dropped,
           "candidates_without_cbp_rows": no_cbp}
    Path(out).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"{len(pop)} candidate metros, {len(rows)} codes, dropped {dropped}, candidates with no CBP rows {no_cbp}")
    return 0


def _norm(s: str) -> str:
    s = s.lower().replace("\u2013", "-").replace(" msa", "").replace("metropolitan area", "").replace("metro area", "")
    return re.sub(r"[^a-z0-9 ,-]", "", s).strip(" ,-")


def match(line: str, cands: list[dict]) -> tuple[str | None, float]:
    """A reply line to a candidate CBSA: exact name, else the best fuzzy score over the full name and over the first
    principal city with its state(s), when at least 0.6."""
    t = _norm(re.sub(r"^\s*(\d+[.)]|[-*\u2022])\s*", "", line))
    best, score = None, 0.0
    for c in cands:
        full = _norm(c["name"])
        if t == full:
            return c["cbsa"], 1.0
        city, _, states = c["name"].partition(", ")
        short = _norm(city.split("-")[0] + ", " + states)
        s = max(difflib.SequenceMatcher(None, t, full).ratio(), difflib.SequenceMatcher(None, t, short).ratio())
        if s > score:
            best, score = c["cbsa"], s
    return (best, round(score, 3)) if score >= 0.6 else (None, round(score, 3))


def claude_arm(truth_file: str, out: str) -> int:
    t = json.loads(Path(truth_file).read_text(encoding="utf-8"))
    exe = shutil.which("claude.exe") or shutil.which("claude.cmd") or shutil.which("claude")
    version = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    rows, models = [], set()
    with tempfile.TemporaryDirectory(prefix="knos-where-") as cwd:
        for r in t["codes"]:
            run = subprocess.run([exe, "-p", PROMPT.format(title=r["title"]), "--output-format", "json", "--strict-mcp-config",
                                  "--mcp-config", NO_MCP], cwd=cwd, capture_output=True, text=True, timeout=600)
            try:
                j = json.loads(run.stdout)
            except ValueError:
                j = {"result": "", "error": (run.stdout + run.stderr)[:300]}
            models |= set((j.get("modelUsage") or {}).keys())
            lines = [x for x in str(j.get("result") or "").splitlines() if x.strip()][:K]
            picked = [dict(zip(("cbsa", "score"), match(x, t["candidates"])), said=x.strip()) for x in lines]
            rows.append({"naics": r["naics"], "said": lines, "matched": picked, "top5": [p["cbsa"] for p in picked if p["cbsa"]]})
            print(r["naics"], [f"{p['said']} -> {p['cbsa']}" for p in picked], flush=True)
    Path(out).write_text(json.dumps({"claude_code": version, "models": sorted(models), "rows": rows}, indent=1), encoding="utf-8")
    return 0


def knos_rank(metros: list[dict], cands: set[str]) -> list[str]:
    rows = [m for m in metros if m["cbsa"] in cands]
    three = sorted((m for m in rows if m["cells"] >= 3), key=lambda m: (-m["affinity"], -m["cells"], m["cbsa"]))
    few = sorted((m for m in rows if m["cells"] < 3), key=lambda m: (-m["affinity"], -m["cells"], m["cbsa"]))
    return [m["cbsa"] for m in (three + few)][:K]


def knos_arm(truth_file: str, out: str) -> int:
    t = json.loads(Path(truth_file).read_text(encoding="utf-8"))
    cands = {c["cbsa"] for c in t["candidates"]}
    rows = []
    for r in t["codes"]:
        req = urllib.request.Request(APP + "/api/check", json.dumps({"idea": r["title"]}).encode(),
                                     {"Content-Type": "application/json", "User-Agent": "knos-test"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            rep = json.loads(resp.read())
        metros = (rep.get("terms") or {}).get("metros") or []
        top5 = knos_rank(metros, cands)
        rows.append({"naics": r["naics"], "cells": (rep.get("terms") or {}).get("heatmap_cells", 0), "top5": top5})
        print(r["naics"], len(metros), "metros", top5, flush=True)
    Path(out).write_text(json.dumps({"rows": rows}, indent=1), encoding="utf-8")
    return 0


def score(truth_file: str, claude_file: str, knos_file: str) -> int:
    t = json.loads(Path(truth_file).read_text(encoding="utf-8"))
    ca = json.loads(Path(claude_file).read_text(encoding="utf-8"))
    kn = json.loads(Path(knos_file).read_text(encoding="utf-8"))
    top10 = {r["naics"]: set(r["top10"]) for r in t["codes"]}
    a = {r["naics"]: len(set(r["top5"][:K]) & top10[r["naics"]]) / K for r in ca["rows"] if r["naics"] in top10}
    b = {r["naics"]: len(set(r["top5"][:K]) & top10[r["naics"]]) / K for r in kn["rows"] if r["naics"] in top10}
    codes = [c for c in top10 if c in a and c in b]
    n = len(codes)
    ma, mb = sum(a[c] for c in codes) / n, sum(b[c] for c in codes) / n
    rng, diffs = random.Random(SEED), []
    for _ in range(BOOT):
        idx = [rng.randrange(n) for _ in codes]
        diffs.append(sum(b[codes[i]] - a[codes[i]] for i in idx) / n)
    diffs.sort()
    lo, hi = diffs[int(0.025 * BOOT)], diffs[int(0.975 * BOOT) - 1]
    sha = hashlib.sha256(PLAN.read_bytes()).hexdigest()
    reading = "Knos with Qloo is ahead" if lo > 0 else "Claude alone is ahead" if hi < 0 else "the test cannot tell them apart"
    doc = {"made": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "plan": "docs/reference/where_truth_plan.md",
           "plan_sha256": sha, "n": n, "dropped": t["dropped"], "metric": "overlap at 5 with the Census top 10, divided by 5",
           "mean_overlap": {"claude_alone": round(ma, 4), "knos_with_qloo": round(mb, 4)}, "difference": round(mb - ma, 4),
           "bootstrap": {"resamples": BOOT, "seed": SEED, "interval_95": [round(lo, 4), round(hi, 4)]}, "reading": reading,
           "claude": {"claude_code": ca.get("claude_code"), "models": ca.get("models")},
           "knos_codes_with_cells": sum(1 for r in kn["rows"] if r.get("cells")),
           "per_code": [{"naics": c, "truth_top10": sorted(top10[c]),
                         "claude_top5": next(r["top5"] for r in ca["rows"] if r["naics"] == c),
                         "knos_top5": next(r["top5"] for r in kn["rows"] if r["naics"] == c), "claude": a[c], "knos": b[c]} for c in codes],
           "sources": {"cbp": "https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23msa.zip",
                       "population": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/metro/totals/cbsa-est2023-alldata.csv",
                       "titles": "https://www2.census.gov/programs-surveys/cbp/technical-documentation/reference/naics-descriptions/naics2017.txt"}}
    PUBLIC.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    lines = [f"plan {doc['plan']} sha256 {sha}", f"claude: {doc['claude']}",
             f"n {n}; mean overlap at 5: Claude alone {ma:.3f}, Knos with Qloo {mb:.3f}; difference {mb - ma:+.3f}, "
             f"95% interval [{lo:+.3f}, {hi:+.3f}]; {reading}",
             f"{'PASS' if n else 'FAIL'} test_where_truth: run once on {n} business types, overlap {ma:.3f} Claude alone vs {mb:.3f} "
             f"Knos with Qloo, difference {mb - ma:+.3f} [{lo:+.3f}, {hi:+.3f}], {reading}"]
    print("\n".join(lines))
    out = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world") / "test_where_truth.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if n else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = {"--truth": truth, "--claude": claude_arm, "--knos": knos_arm, "--score": score}[args[0]]
    sys.exit(mode(*args[1:]))
