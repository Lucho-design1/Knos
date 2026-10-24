"""test_kickstarter_truth, live: 500 past Kickstarter projects (launched 2019-2023, state successful or failed) from the
webrobots.io dump of 2026-10-12, drawn per main category in proportion (at least 1 each, seed 0) and split 250 tune /
250 held-out (stratified by state, seed 0). Knos reads only the name, blurb and category, through two predictors:
(a) open signals, POST /api/open-signals, verdict OPEN; (b) open signals + Qloo, POST /api/check, decision.verdict OPEN.
The tune half picks one thing per predictor: whether OPEN means success or failure. The held-out half is scored:
accuracy, the majority-class base rate, an exact one-sided binomial test against it and Fisher's exact test on the 2x2.
Pass: all 500 rows got both predictions and the stats were computed. The result is published as measured.

    python -I scripts/test_kickstarter_truth.py --build <Kickstarter_*.json.gz> <ks-sample.json>   (the sample, once)
    KNOS_ADMIN_KEY=... python scripts/test_kickstarter_truth.py <ks-sample.json> [--limit N] [--cache file] [--part i/n]

Resumable: rows already in the cache (default ks-cache.json next to the sample) are not asked again. A full run (no
--limit) writes its output to test_kickstarter_truth.txt next to the sample and, on a pass, the summary (numbers,
method, source; no project texts, no Qloo answers) to docs/reference/kickstarter_truth.json.
"""
from __future__ import annotations

import datetime
import gzip
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outside_truth import binom_ge, fisher, post  # noqa: E402

PUBLIC = os.path.join(os.path.dirname(__file__), "..", "docs", "reference", "kickstarter_truth.json")
DUMP = "Kickstarter_2026-10-12T07_08_07_724Z.json.gz"
SOURCE = {"name": "webrobots.io Kickstarter datasets, the dump of 2026-10-12 (JSON)", "page": "https://webrobots.io/kickstarter-datasets/",
          "url": "https://s3.amazonaws.com/weruns/forfun/Kickstarter/" + DUMP, "bytes": 103012169,
          "sha256": "e27490898e74ed929e02dffba21a98c067d83a5cf953aca4ebd556852b99b80b"}
KEEP = ("successful", "failed")
FROM, TO = datetime.date(2019, 1, 1), datetime.date(2023, 12, 31)
N, SEED = 500, 0
PREDICTORS = {"open_signals": "/api/open-signals", "open_signals_qloo": "/api/check"}
METHOD = ("Population: Kickstarter projects in the webrobots.io dump of 2026-10-12, state successful or failed, launched "
          "2019-01-01 to 2023-12-31 (UTC), one record per project id. 500 drawn per main category in proportion (at least 1 "
          "each, seed 0), split 250 tune / 250 held-out stratified by state (seed 0). Knos sees one line: 'name: blurb' cut "
          "to 200 characters, then ' (main/sub category)' (neither API has a category field). Predictor (a): verdict of POST "
          "/api/open-signals; (b): decision.verdict of POST /api/check (open signals + Qloo). A 400 counts as REFUSE. Tuned on "
          "the tune half and nothing else: per predictor, whether OPEN predicts success or failure (the more accurate one; a "
          "tie keeps OPEN = success); every other verdict predicts the opposite. Scored on the held-out half: accuracy, the "
          "majority-class base rate, exact binomial p (one-sided, accuracy above the base rate), Fisher's exact p (two-sided).")


def _when(v) -> datetime.date:
    return datetime.datetime.fromtimestamp(int(v), datetime.timezone.utc).date()


def build(dump: str, out: str) -> int:
    """The sample from the dump: filter, one record per id, 500 per main category in proportion, then the split."""
    seen, pool = set(), []
    with gzip.open(dump, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line).get("data") or {}
            pid = str(d.get("id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            if d.get("state") not in KEEP or not d.get("launched_at") or not FROM <= _when(d["launched_at"]) <= TO:
                continue
            c = d.get("category") or {}
            main = c.get("parent_name") or c.get("name") or "?"
            pool.append({"id": pid, "name": " ".join(str(d.get("name") or "").split()),
                         "blurb": " ".join(str(d.get("blurb") or "").split()),
                         "category": {"main": main, "sub": c.get("name") or main}, "state": d["state"],
                         "launched_at": _when(d["launched_at"]).isoformat()})
    pool.sort(key=lambda r: int(r["id"]) if r["id"].isdigit() else 0)
    by: dict[str, list[dict]] = {}
    for r in pool:
        by.setdefault(r["category"]["main"], []).append(r)
    cats = sorted(by)
    exact = {c: N * len(by[c]) / len(pool) for c in cats}
    quota = {c: max(1, int(exact[c])) for c in cats}
    for c in sorted(cats, key=lambda c: (-(exact[c] - int(exact[c])), c)):        # largest remainders fill up to 500
        if sum(quota.values()) >= N:
            break
        quota[c] += 1
    while sum(quota.values()) > N:                                                  # the at-least-1 floor overshot
        c = max((c for c in cats if quota[c] > 1), key=lambda c: (quota[c] - exact[c], c))
        quota[c] -= 1
    rng = random.Random(SEED)
    rows = [r for c in cats for r in rng.sample(by[c], quota[c])]
    rng = random.Random(SEED)
    odd = 0
    for st in KEEP:                                                                 # half of each state to each side
        part = [r for r in rows if r["state"] == st]
        rng.shuffle(part)
        k = len(part) // 2 + (len(part) % 2 if odd == 0 else 0)
        odd ^= len(part) % 2
        for i, r in enumerate(part):
            r["split"] = "tune" if i < k else "held_out"
    rows.sort(key=lambda r: (r["split"] != "tune", r["category"]["main"], int(r["id"]) if r["id"].isdigit() else 0))
    succ = sum(1 for r in pool if r["state"] == "successful")
    meta = {"source": SOURCE, "made": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "population": len(pool), "population_success_rate": round(succ / len(pool), 4),
            "quota": quota, "seed": SEED,
            "sample_success_rate": round(sum(1 for r in rows if r["state"] == "successful") / len(rows), 4),
            "split": {s: {st: sum(1 for r in rows if r["split"] == s and r["state"] == st) for st in KEEP} for s in ("tune", "held_out")}}
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rows": rows}, f, indent=1)
    print(json.dumps(meta, indent=1))
    return 0


def idea(row: dict) -> str:
    t = f"{row['name']}: {row['blurb']}".strip()
    if len(t) > 200:
        t = t[:200].rsplit(" ", 1)[0]
    c = row["category"]
    return t + f" ({c['main']}/{c['sub']})" if c["sub"] != c["main"] else t + f" ({c['main']})"


def ask(path: str, text: str, headers: dict) -> tuple[str | None, str]:
    """One predictor's verdict: OPEN, another verdict, REFUSE (a 400), or None with the reason after 5 retries."""
    st, got = 0, {}
    for _ in range(6):
        st, got = post(path, {"idea": text}, headers, timeout=300)
        if st == 429:
            time.sleep(70)
        elif st >= 500:                                                             # a 5xx or no answer (599)
            time.sleep(20)
        else:
            break
    if st == 400:
        return "REFUSE", str(got.get("message") or got.get("error") or "")[:160]
    v = (got.get("decision") or {}).get("verdict") if path == "/api/check" else got.get("verdict")
    if st == 200 and isinstance(v, str) and v:
        return v, ""
    return None, f"HTTP {st} {str(got.get('message') or got.get('error') or '')[:80]}"


def score(rows: list[dict], open_means: bool) -> dict:
    done = [{"pred": (r["verdict"] == "OPEN") == open_means, "truth": r["truth"]} for r in rows]
    n = len(done)
    tp = sum(1 for r in done if r["pred"] and r["truth"])
    fp = sum(1 for r in done if r["pred"] and not r["truth"])
    fn = sum(1 for r in done if not r["pred"] and r["truth"])
    tn = n - tp - fp - fn
    pos = tp + fn
    base = max(pos, n - pos) / n if n else 0.0
    return {"rows": n, "successful": pos, "failed": n - pos, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "accuracy": round((tp + tn) / n, 4) if n else None, "base_rate": round(base, 4),
            "p_binomial_vs_base": round(binom_ge(tp + tn, n, base), 6) if n else None,
            "p_fisher": round(fisher(tp, fp, fn, tn), 6) if n else None,
            "verdicts": {v: sum(1 for r in rows if r["verdict"] == v) for v in sorted({r["verdict"] for r in rows})}}


def main(sample_path: str, limit: int | None, cache: str | None, part: tuple[int, int] | None = None) -> int:
    sample = json.loads(open(sample_path, encoding="utf-8").read())
    rows = sample["rows"]
    todo = rows[:limit] if limit else rows
    if part:                                                                        # one of n workers, its own cache
        todo = [r for i, r in enumerate(todo) if i % part[1] == part[0]]
        limit = limit or len(todo)
    world = os.path.dirname(os.path.abspath(sample_path))
    cache = cache or os.path.join(world, "ks-cache.json")
    res = json.loads(open(cache, encoding="utf-8").read()) if os.path.exists(cache) else {"rows": {}}
    key = os.environ.get("KNOS_ADMIN_KEY", "")
    op = {"X-Knos-Admin": key} if key else {}                                       # the operator's run: past the per-address limits
    lines: list[str] = []

    def say(s: str) -> None:
        print(s, flush=True)
        lines.append(s)

    say(f"test_kickstarter_truth {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M UTC} on {os.environ.get('KNOS_WANTED_URL', 'https://knos.onrender.com')}"
        f", {len(todo)} of {len(rows)} rows, admin key {'set' if key else 'not set'}")
    for i, row in enumerate(todo, 1):
        got = res["rows"].setdefault(row["id"], {})
        text = idea(row)
        for name, path in PREDICTORS.items():
            if got.get(name):
                continue
            v, why = ask(path, text, op)
            if v:
                got[name] = v
                if why:                                                             # why it was refused (private cache only)
                    got[name + "_why"] = why
            else:
                say(f"MISS {row['id']} {name}: {why}")
            with open(cache, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=1)
            time.sleep(1)
        say(f"{i:3} {row['split'][:4]:4} {row['state'][:4]:4} {str(got.get('open_signals')):13} {str(got.get('open_signals_qloo')):13} {row['category']['main']}")
    have = [r for r in todo if all(res["rows"].get(r["id"], {}).get(p) for p in PREDICTORS)]
    out: dict = {}
    for name in PREDICTORS:
        part = {s: [{"verdict": res["rows"][r["id"]][name], "truth": r["state"] == "successful"} for r in have if r["split"] == s]
                for s in ("tune", "held_out")}
        yes, no = score(part["tune"], True), score(part["tune"], False)
        open_means = not (no["accuracy"] or 0) > (yes["accuracy"] or 0)
        out[name] = {"tuned": {"open_means": "successful" if open_means else "failed",
                               "tune_accuracy": {"open_means_successful": yes["accuracy"], "open_means_failed": no["accuracy"]},
                               "tune_rows": len(part["tune"])},
                     "held_out": score(part["held_out"], open_means)}
    full = len(have) == len(rows) == N and not limit
    for name, s in out.items():
        h = s["held_out"]
        say(f"{name}: OPEN means {s['tuned']['open_means']} (tune {s['tuned']['tune_accuracy']}); held-out n={h['rows']} accuracy "
            f"{h['accuracy']} vs base rate {h['base_rate']}, p binomial {h['p_binomial_vs_base']}, p Fisher {h['p_fisher']}, "
            f"tp {h['tp']} fp {h['fp']} fn {h['fn']} tn {h['tn']}, verdicts {h['verdicts']}")
    nums = "; ".join(f"{k} acc {v['held_out']['accuracy']} vs base {v['held_out']['base_rate']} p_binom {v['held_out']['p_binomial_vs_base']} "
                     f"p_fisher {v['held_out']['p_fisher']}" for k, v in out.items())
    if full:
        doc = {"made": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "summary": {"held_out_rows": out["open_signals"]["held_out"]["rows"], "tune_rows": out["open_signals"]["tuned"]["tune_rows"],
                           "sample_success_rate": sample["meta"]["sample_success_rate"],
                           "population": sample["meta"]["population"], "population_success_rate": sample["meta"]["population_success_rate"],
                           "predictors": out},
               "method": METHOD, "source": SOURCE}
        with open(PUBLIC, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
        say("PASS test_kickstarter_truth: " + nums)
    else:
        why = f"--limit {limit}: " if limit else ""
        say(f"FAIL test_kickstarter_truth: {why}{len(have)} of {len(rows)} rows have both predictions ({nums})")
    if not limit:
        with open(os.path.join(world, "test_kickstarter_truth.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0 if full else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--build":
        sys.exit(build(a[1], a[2]))
    sys.exit(main(a[0], int(a[a.index("--limit") + 1]) if "--limit" in a else None,
                  a[a.index("--cache") + 1] if "--cache" in a else None,
                  tuple(int(x) for x in a[a.index("--part") + 1].split("/")) if "--part" in a else None))  # type: ignore[arg-type]
