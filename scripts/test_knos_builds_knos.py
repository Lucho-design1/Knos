"""test_knos_builds_knos, live: the brief that set this work is a Knos project, and each of its
milestones was released on devnet only after its test passed in CI.

    python scripts/test_knos_builds_knos.py <project id> [--except <check>]

For every milestone (but the one named by --except: the CI job of this very test runs before its own release):
  - the app says it is released, to its CI attempt, at a commit of the bound repository;
  - GitHub's own record of that check run: GitHub Actions, the milestone's exact check name, that commit, success;
  - the commit is on the repository's default branch;
  - every order on it is released, and devnet holds each release transaction without an error;
  - the release came after the check run completed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime

APP = os.environ.get("APP_URL", "https://knos.onrender.com").rstrip("/")
RPC = "https://api.devnet.solana.com"


def get(url: str, data: dict | None = None):
    req = urllib.request.Request(url, data=None if data is None else json.dumps(data).encode(),
                                 headers={"User-Agent": "knos-test", "Accept": "application/json", "Content-Type": "application/json"})
    tok = os.environ.get("GITHUB_TOKEN") if url.startswith("https://api.github.com/") else None
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - the app, GitHub and devnet
        return json.loads(r.read())


def when(s: str | None) -> float:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() if s else 0.0


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    pid, skip = argv[0], (argv[argv.index("--except") + 1] if "--except" in argv else None)
    fails = 0

    def ok(c: bool, msg: str) -> None:
        nonlocal fails
        print(("ok   " if c else "FAIL ") + msg)
        fails += 0 if c else 1

    p = get(f"{APP}/api/project?id={pid}")
    repo = p.get("repo")
    ok(bool(repo), f"project {pid}: bound to {repo}, {len(p['milestones'])} milestones")
    print(f"     {APP}/#projects={pid}")
    released = 0
    for m in p["milestones"]:
        check = (m.get("verifier") or {}).get("check")
        if check == skip:
            print(f"     {check}: this run's own milestone, released after this job")
            continue
        a = next((x for x in m["attempts"] if x["id"] == m.get("ci_attempt")), {})
        ci = a.get("ci") or {}
        if m["status"] != "released" or not ci:
            ok(False, f"{check}: {m['status']}, not released on a CI check")
            continue
        run = get(f"https://api.github.com/repos/{repo}/check-runs/{ci['run_id']}")
        good = (run.get("name") == check and (run.get("app") or {}).get("slug") == "github-actions"
                and run.get("head_sha") == ci["sha"] and run.get("conclusion") == "success")
        branch = get(f"https://api.github.com/repos/{repo}").get("default_branch", "main")
        on = get(f"https://api.github.com/repos/{repo}/compare/{ci['sha']}...{branch}").get("status") in ("ahead", "identical")
        sigs = [s for o in m["orders"] for k, s in (o.get("signatures") or {}).items() if k.startswith("referee") and s]
        txs = [get(RPC, {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                         "params": [s, {"commitment": "confirmed", "maxSupportedTransactionVersion": 1, "encoding": "json"}]}).get("result")
               for s in sigs]
        chain = bool(sigs) and all(t and t["meta"]["err"] is None for t in txs) and all(o["status"] == "released" for o in m["orders"])
        after = bool(txs) and all(t and t.get("blockTime", 0) >= when(run.get("completed_at")) for t in txs)
        ok(good and on and chain and after, f"{check}: released at {ci['sha'][:12]} after {run.get('html_url')} "
           f"({run.get('conclusion')}); {len(sigs)} devnet release(s) {', '.join(s[:16] for s in sigs)}")
        released += good and on and chain and after
    want = len(p["milestones"]) - (1 if skip else 0)
    print(f"released on a passing CI check: {released} of {want}" + (" (and this run's own milestone after it)" if skip else ""))
    print("FAIL test_knos_builds_knos" if fails or released < want else "PASS test_knos_builds_knos")
    return 1 if fails or released < want else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
