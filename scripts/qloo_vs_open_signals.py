"""test_qloo_vs_open_signals, live: 20 ideas from 10 fields, each answered twice by the hosted app: from open signals only
(POST /api/open-signals: Wikimedia, GDELT, Hacker News, OpenAlex, World Bank, Wikidata; keyless, no Qloo) and with Qloo
added (POST /api/check). A row changes when Qloo changes the verdict, the audience, the launch cities or the price tier.
Pass: at least 15 of 20 change. The table is published as measured, whatever it shows.

    KNOS_ADMIN_KEY=... python scripts/qloo_vs_open_signals.py [--publish]

Each Qloo run's trace is kept on devnet (POST /api/trace/keep), so the page's links survive a redeploy; each open signal
keeps the public link it was read from. Qloo's answers stay on the server: nothing of them is written into this
repository. With --publish the table replaces the one on "With and without Qloo" (POST /api/qloo-diff, the operator's key).
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("KNOS_WANTED_URL", "https://knos.onrender.com")
IDEAS = [("energy", "a perovskite solar roof tile for homes"), ("energy", "a home battery that charges from the grid at night"),
         ("materials", "a self-healing concrete for driveways"), ("materials", "a graphene-coated cycling jacket"),
         ("biotech", "a sweat glucose sensor fitness watch"), ("biotech", "a probiotic skincare serum"),
         ("quantum", "a quantum computing course for teenagers"), ("quantum", "a quantum random number generator USB key"),
         ("PQC", "a post-quantum encrypted messaging app"), ("PQC", "a post-quantum VPN for small businesses"),
         ("AI", "an AI tutor for high school math"), ("AI", "an AI recipe planner for families"),
         ("Web3", "a crypto wallet for teenagers"), ("Web3", "an NFT ticketing app for concerts"),
         ("consumer", "a smart water bottle that glows to remind you to drink"), ("consumer", "a recovery shoe for marathon runners"),
         ("food", "a plant-based burger chain"), ("food", "a fermented hot sauce subscription"),
         ("media", "a true-crime podcast about art heists"), ("media", "a documentary series about ocean plastic")]
RULE = ("Changed = with Qloo added, the verdict differs from the open signals' verdict, or Qloo names an audience (age and "
        "gender), launch cities or a price tier that the open signals do not (scripts/qloo_vs_open_signals.py).")


def post(path, body, headers=None, timeout=300):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def with_qloo(rep: dict) -> dict:
    d = rep.get("decision") or {}
    plan, g = d.get("plan") or {}, rep.get("grounding") or {}
    who = plan.get("who") or {}
    aud = ", ".join(x for x in (who.get("age"), who.get("gender")) if x) or g.get("audience") or ""
    tier = (rep.get("price") or {}).get("tier") or plan.get("tier") or g.get("price_tier") or ""
    return {"hash": rep.get("hash"), "verdict": d.get("verdict"), "audience": str(aud).replace("_", " "),
            "cities": [c.get("name") for c in (rep.get("cities") or [])][:3] or (plan.get("where") or [])[:3], "tier": tier}


def open_only(b: dict) -> dict:
    """The open signals, compact (the page rebuilds each source's public link from the subject phrase): source, the value
    it gave (None: no answer), whether it counts, and the article or concept it found."""
    keys = {"Wikimedia pageviews": "views_per_day", "GDELT news": "articles_3_months", "Hacker News": "stories_2_years",
            "OpenAlex": "works_since_2023", "World Bank": "gdp_per_person_usd", "Wikidata": "id"}
    sig = [[x.get("source"), x.get(keys.get(x.get("source"), ""), None) if x.get("answered") else None, bool(x.get("counts")),
            x.get("article") or x.get("label") or ""] for x in b.get("signals") or []]
    return {"verdict": b.get("verdict"), "audience": "", "cities": [], "tier": b.get("price_tier") or "", "phrase": b.get("phrase"),
            "counted": b.get("attention_counted"), "signals": sig}


def claude_side(a: dict) -> dict | None:
    """The first arm (scripts/llm_baseline.py): Claude alone, no tools and no data, in the same four fields."""
    if not a or not a.get("verdict"):
        return None
    return {k: a.get(k) for k in ("verdict", "audience", "cities", "tier", "why", "model")}


def main(publish: bool, claude_file: str | None = None) -> int:
    rows, rules = [], None
    claude = json.loads(open(claude_file, encoding="utf-8").read()) if claude_file else {}
    op = {"X-Knos-Admin": os.environ.get("KNOS_ADMIN_KEY", "")}           # the operator's run: past the per-address limits
    for field, idea in IDEAS:
        s1, base = post("/api/open-signals", {"idea": idea}, op)
        s2, rep = post("/api/check", {"idea": idea}, op)
        if s1 != 200 or s2 != 200:
            print(f"FAIL {field}: {idea}: HTTP {s1}/{s2} {base.get('message') or rep.get('message')}")
            return 1
        rules = base.get("rules")
        a, b = with_qloo(rep), open_only(base)
        changed = [k for k in ("verdict", "audience", "cities", "tier") if a[k] != b[k]]
        post("/api/trace/keep", {"hash": a["hash"]}, op)
        row = {"field": field, "idea": idea, "with": a, "open": b, "changed": changed}
        c = claude_side(claude.get(idea))
        if c:
            row["claude"] = c
            row["claude_vs_qloo"] = [k for k in ("verdict", "audience", "cities", "tier") if c[k] != a[k]]
        rows.append(row)
        print(f"{'changed' if changed else 'same   '} {field:9} {idea[:44]:44} open: {b['verdict']}, {b['tier'] or '-'} ({b['counted']} of 4) "
              f"| with Qloo: {a['verdict']}, {a['audience'] or '-'}, {'/'.join(a['cities']) or '-'}, {a['tier'] or '-'} | {','.join(changed) or '-'}", flush=True)
        time.sleep(1)
    n = sum(1 for r in rows if r["changed"])
    s = {"rows": len(rows), "changed": n, **{k: sum(1 for r in rows if k in r["changed"]) for k in ("verdict", "audience", "cities", "tier")}}
    arms = [r for r in rows if r.get("claude")]
    if arms:                                   # how often Claude alone said the same as Knos with Qloo, field by field
        s["claude"] = {"rows": len(arms), **{f"{k}_same_as_qloo": sum(1 for r in arms if k not in r["claude_vs_qloo"])
                                             for k in ("verdict", "audience", "cities", "tier")},
                       "verdict_same_as_open_signals": sum(1 for r in arms if r["claude"]["verdict"] == r["open"]["verdict"])}
        print("Claude alone vs with Qloo: " + json.dumps(s["claude"]))
    print(f"{n} of {len(rows)} changed with Qloo added: {json.dumps(s)}")
    if publish:
        st, got = post("/api/qloo-diff", {"made": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "summary": s,
                                          "rows": rows, "rule": RULE, "rules": rules,
                                          "baseline": "open signals" + (", and Claude alone (claude -p: no tools, no data)" if arms else "")}, op)
        print(f"published: HTTP {st} {got}")
        if st != 200:
            return 1
    ok = n >= 15
    print("PASS test_qloo_vs_open_signals" if ok else "FAIL test_qloo_vs_open_signals (fewer than 15 of 20 changed; published as measured)")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main("--publish" in args, args[args.index("--claude") + 1] if "--claude" in args else None))
