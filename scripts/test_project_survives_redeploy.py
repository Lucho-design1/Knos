"""M1 test_project_survives_redeploy, live: a project opened on the hosted app returns HTTP 200 with the same criteria
hash after the app is redeployed by commit id.

    RENDER_API_KEY=... python scripts/test_project_survives_redeploy.py <render service id> <commit sha>

1. a guest (the app's unverified label, no account) opens a project with a Ready brief; its criteria hash is kept;
2. the project's SPL Record account appears on devnet (knos_wanted.chainstate: authority = the app's relayer);
3. the app is redeployed by commit id (Render API, POST /deploys {commitId}), and the deploy goes live;
4. GET /api/project?id= answers 200, with the same criteria hash.
The key is read from the environment and never printed. Exit 0 only when all four hold.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("KNOS_WANTED_URL", "https://knos.onrender.com")
RPC = "https://api.devnet.solana.com"
RECORD = "recr1L3PCGKLbckBqMNcJhuuyU1zgo8nBhfLVsJNwr5"
BRIEF = {"milestones": [{"key": "m1", "name": "Recovery shoe sell-through in Austin", "target": "200 pairs sold in 60 days on test_sell_through",
                         "verifier": {"kind": "machine", "check": "ci / test_sell_through"}, "deadline_days": 14}]}


def http(method: str, url: str, body=None, headers=None, timeout=60):
    req = urllib.request.Request(url, None if body is None else json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:200].decode("utf-8", "replace")}


def records_naming(pid: str, authority: str) -> list[str]:
    """Record accounts of the relayer whose data names this project (the key follows the magic and the kind)."""
    import base64
    _, got = http("POST", RPC, {"jsonrpc": "2.0", "id": 1, "method": "getProgramAccounts", "params": [RECORD, {
        "encoding": "base64", "commitment": "confirmed", "filters": [{"memcmp": {"offset": 1, "bytes": authority}}]}]})
    return [a["pubkey"] for a in got.get("result") or [] if pid.encode() in base64.b64decode(a["account"]["data"][0])[33:80]]


def main(service: str, sha: str) -> int:
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        print("RENDER_API_KEY is not set")
        return 2
    render = {"Authorization": "Bearer " + key}
    tok = http("POST", BASE + "/api/auth/guest", {"label": "test_project_survives_redeploy"})[1]["token"]
    st, p = http("POST", BASE + "/api/project", {"template": "custom", "title": "Survives a redeploy (test)", "brief": BRIEF},
                 {"Authorization": "Bearer " + tok})
    pid = p.get("id")
    before = (http("GET", f"{BASE}/api/project?id={pid}")[1].get("ready") or {}).get("criteria_hash")
    print(f"1. opened {pid} (HTTP {st}), criteria {str(before)[:16]}")
    authority = http("GET", BASE + "/api/status")[1].get("relayer") or os.environ.get("KNOS_RELAYER", "FRXXJkfpwasEpttH5dvDwkySuJzL5D5swjA52U7TMeRD")
    for _ in range(40):
        got = records_naming(pid, authority)
        if got:
            break
        time.sleep(3)
    print(f"2. its record on devnet: {got[0] if got else 'none'}")
    st, d = http("POST", f"https://api.render.com/v1/services/{service}/deploys", {"commitId": sha}, render)
    dep = d.get("id")
    print(f"3. redeploy {dep} of {sha[:8]} (HTTP {st})", flush=True)
    status = None
    for _ in range(80):
        status = http("GET", f"https://api.render.com/v1/services/{service}/deploys/{dep}", headers=render)[1].get("status")
        if status in ("live", "build_failed", "update_failed", "canceled", "deactivated"):
            break
        time.sleep(15)
    print(f"   deploy {status}")
    for _ in range(20):                                   # the new instance takes the traffic a moment after "live"
        st, after = http("GET", f"{BASE}/api/project?id={pid}")
        if st == 200:
            break
        time.sleep(6)
    now = (after.get("ready") or {}).get("criteria_hash") if st == 200 else None
    ok = bool(got) and status == "live" and st == 200 and now == before and before
    print(f"4. after the redeploy: HTTP {st}, criteria {str(now)[:16]}, same: {now == before}")
    print("PASS test_project_survives_redeploy" if ok else "FAIL test_project_survives_redeploy")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
