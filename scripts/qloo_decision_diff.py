"""M2 test_qloo_decision_diff, live: 20 ideas from 10 fields, each run through the hosted demand check with Qloo and with
the Qloo key unset (POST /api/check {"without_qloo": true}: the same server and code, no key). A row changes when Qloo
changes the verdict, the audience, the launch cities or the price tier. Pass: at least 15 of 20 change.

    KNOS_ADMIN_KEY=... python scripts/qloo_decision_diff.py [--publish]

Both traces of every row are kept on devnet (POST /api/trace/keep) so the page's links survive a redeploy; with
--publish the table is published to the "With and without Qloo" page (POST /api/qloo-diff, the operator's key). Qloo's
answers stay on the server: nothing of them is written into this repository.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
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
RULE = ("Changed = the verdict differs, or the audience (age and gender), the launch cities or the price tier differ between "
        "the run with Qloo and the run with the key unset (scripts/qloo_decision_diff.py).")


def post(path, body, headers=None, timeout=300):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def summary(rep: dict) -> dict:
    d = rep.get("decision") or {}
    plan, g = d.get("plan") or {}, rep.get("grounding") or {}
    who = plan.get("who") or {}
    aud = ", ".join(x for x in (who.get("age"), who.get("gender")) if x) or g.get("audience") or ""
    return {"hash": rep.get("hash"), "verdict": d.get("verdict"), "audience": str(aud).replace("_", " "),
            "cities": (plan.get("where") or g.get("cities") or [])[:3], "tier": plan.get("tier") or g.get("price_tier") or ""}


def main(publish: bool) -> int:
    rows = []
    for field, idea in IDEAS:
        s1, with_ = post("/api/check", {"idea": idea})
        s2, without = post("/api/check", {"idea": idea, "without_qloo": True})
        if s1 != 200 or s2 != 200:
            print(f"FAIL {field}: {idea}: HTTP {s1}/{s2} {with_.get('error') or without.get('error')}")
            return 1
        a, b = summary(with_), summary(without)
        changed = [k for k in ("verdict", "audience", "cities", "tier") if a[k] != b[k]]
        for h in (a["hash"], b["hash"]):
            post("/api/trace/keep", {"hash": h})
        rows.append({"field": field, "idea": idea, "with": a, "without": b, "changed": changed})
        print(f"{'changed' if changed else 'same   '} {field:9} {idea[:46]:46} with: {a['verdict']}, {a['audience'] or '-'}, "
              f"{'/'.join(a['cities']) or '-'}, {a['tier'] or '-'} | unset: {b['verdict']} | {','.join(changed) or '-'}", flush=True)
    n = sum(1 for r in rows if r["changed"])
    s = {"rows": len(rows), "changed": n, **{k: sum(1 for r in rows if k in r["changed"]) for k in ("verdict", "audience", "cities", "tier")}}
    print(f"{n} of {len(rows)} changed with Qloo: {json.dumps(s)}")
    if publish:
        key = os.environ.get("KNOS_ADMIN_KEY", "")
        st, got = post("/api/qloo-diff", {"made": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "summary": s,
                                          "rows": rows, "rule": RULE}, {"X-Knos-Admin": key})
        print(f"published: HTTP {st} {got}")
        if st != 200:
            return 1
    ok = n >= 15
    print("PASS test_qloo_decision_diff" if ok else "FAIL test_qloo_decision_diff (fewer than 15 of 20 changed; published as measured)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main("--publish" in sys.argv[1:]))
