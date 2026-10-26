"""test_who_wants_it, live: over the 20 ideas of the Qloo comparison, "Who wants it" shows Qloo audiences tied to the
idea: asked of /v2/insights (filter.type=urn:audience) with signal.interests.tags set to the idea's own matched Qloo
tags (the matched products when it has none). Passes when >= 15 of 20 ideas show >= 1 audience and every audience
shown names a tie that is one of that report's own tags or matched products, sits above Qloo's neutral affinity
(0.55; a tag alone answered 0.5 with the same three audiences for every idea), and no one audience list repeats across
all the ideas.

    KNOS_ADMIN_KEY=... python scripts/test_who_wants_it.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qloo_vs_open_signals import IDEAS  # noqa: E402

APP = "https://knos.onrender.com"
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
OP = {"X-Knos-Admin": os.environ.get("KNOS_ADMIN_KEY", "")}


def main() -> int:
    lines, showing, untied, sets = [], 0, [], []
    for _, idea in IDEAS:
        req = urllib.request.Request(APP + "/api/check", json.dumps({"idea": idea}).encode(), {"Content-Type": "application/json", **OP})
        rep = json.loads(urllib.request.urlopen(req, timeout=300).read())
        ties = {t.get("id") for t in rep.get("tags") or []} | {m.get("id") for m in rep.get("matches") or []} | \
            ({(rep.get("leader") or {}).get("id")} if rep.get("leader") else set())
        wants = rep.get("who_wants") or []
        bad = [a.get("name") for a in wants if (a.get("tie") or {}).get("id") not in ties - {None}
               or not isinstance(a.get("affinity"), (int, float)) or a["affinity"] <= 0.55]
        sets.append(tuple(sorted(a.get("name") or "" for a in wants)))
        untied += [f"{idea}: {b}" for b in bad]
        showing += bool(wants)
        lines.append(f"{idea[:44]:44} {len(wants)} audience(s): " +
                     "; ".join(f"{a['name']} {a['affinity']:.2f} (Qloo {a['tie']['kind']} {a['tie']['name']}{', through ' + a['tie']['via'] if a['tie'].get('via') else ''})" for a in wants[:3]))
    shown = [x for x in sets if x]
    same = max((shown.count(x) for x in shown), default=0)
    ok = showing >= 15 and not untied and same < len(shown)
    lines.append(("PASS" if ok else "FAIL") + f" test_who_wants_it: {showing} of {len(IDEAS)} ideas show >= 1 audience, "
                 f"{len(untied)} untied or neutral {untied[:3]}, {len(set(shown))} distinct audience lists")
    print("\n".join(lines))
    (WORLD / "test_who_wants_it.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
