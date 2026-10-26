"""test_live_crossing, live: the crossing's page on the front door (Pages at the commit under test) shows the criteria
hash, which is the hash of the brief the project holds; every transaction it links is confirmed on devnet; each
release says what released it as its own transaction says.

    python scripts/test_live_crossing.py <project id> <commit sha under test>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src"), str(ROOT / "apps" / "wanted")]
import crossing_page as cp  # noqa: E402

WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
OUT = WORLD / "test_live_crossing.txt"


def main(pid: str, sha: str) -> int:
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    dep = json.loads(subprocess.run(["gh", "api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"],
                                    capture_output=True, text=True, check=True).stdout)[0]
    ok(dep["sha"] == sha, f"Pages deployed at {dep['sha'][:7]} (commit under test {sha[:7]})")
    with urllib.request.urlopen(f"https://drexthealpha.github.io/Knos/crossing/{pid}/?t={int(time.time())}", timeout=60) as r:
        page = r.read().decode("utf-8")
    f = cp.facts(pid)
    d = f["demand"]
    lines.append(f"idea {d['idea']}, city {d['city']}, affinity {d['affinity']}, population {d['population']}, T {d['target']} "
                 f"(the smallest D2 target; tied with a fermented hot sauce subscription at 10, the first in the T2 list taken)")
    ok(f["criteria_hash"] in page and f["criteria_hash"] == f["recomputed"] and "the same" in page,
       f"the page shows the criteria hash {f['criteria_hash'][:16]}..., recomputed from the project's brief: the same")
    sigs = re.findall(r"explorer\.solana\.com/tx/([1-9A-HJ-NP-Za-km-z]{64,90})\?cluster=devnet", page)
    good = [s for s in sigs if (cp.tx(s) or {}).get("meta", {"err": 1}).get("err") is None]
    ok(len(sigs) == 20 and len(good) == 20, f"{len(good)} of {len(sigs)} linked transactions confirmed on devnet (10 pre-orders held, 10 releases)")
    ok(len(f["wallets"]) >= 3 and len(f["orders"]) == d["target"], f"{len(f['orders'])} pre-orders = T {d['target']}, from {len(f['wallets'])} wallets")
    labels = {r["release"]: r["released_by"] for r in f["orders"]}
    shown = all(lab and f'{r}?cluster=devnet">{lab}' in page.replace("&#x27;", "'") for r, lab in labels.items())
    ok(shown and f["status"] == "released", f"each release says what released it, read from its transaction: {sorted(set(labels.values()))}; milestone {f['status']}")
    lines.append(f"FAIL test_live_crossing: {fails} check(s) failed" if fails else
                 f"PASS test_live_crossing: T {d['target']} pre-orders from {len(f['wallets'])} wallets held and released on devnet, 20 of 20 transactions confirmed, hash matches the brief")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
