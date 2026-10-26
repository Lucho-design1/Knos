"""test_agent_solver, live: an outside agent that holds ONLY a capped, revocable agent key claims the
funded autoresearch milestone, submits a train.py to the round's sealed referee and is paid on devnet, with 0 human
clicks after the key is made. Devnet test money only.

    KNOS_ADMIN_KEY=... python scripts/test_agent_solver.py

  0. the operator (its X-Knos-Admin key): the solver brief "autoresearch_round" is open and funded, else it is opened
     (action solver_open) and funded from the app's devnet test wallet (action solver_fund), as the champion project was;
  1. the owner: a guest session (POST /api/auth/guest) makes a key capped at 1 claim and 10 test units, paid at a fresh
     devnet address (solders Keypair; only its public key is kept, so nothing can spend from it);
  2. with ONLY the key: an OAuth 2.0 token (client credentials), tools/list, knos_tasks (the round's README says what to
     change), knos_project_claim, knos_milestone_submit with the baseline train.py changed as the README says, the wait
     for the release, and the payout address's test-unit balance read from devnet's public RPC;
  3. a write call with no credential is refused; the owner revokes the key; the key and its token are refused.
Prints one PASS or FAIL line per check, never a key or a token; exits 1 on any FAIL. Stdlib, and solders for the address.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("KNOS_WANTED_URL", "https://knos.onrender.com").rstrip("/")
RPC = os.environ.get("KNOS_DEVNET_RPC", "https://api.devnet.solana.com")
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
BRIEF = "autoresearch_round"
FAILS: list[str] = []


def ok(cond, what: str) -> bool:
    print(("PASS " if cond else "FAIL ") + what, flush=True)
    if not cond:
        FAILS.append(what)
    return bool(cond)


def http(path, body=None, token=None, headers=None, form=None, timeout=300):
    h = {"Content-Type": "application/x-www-form-urlencoded" if form is not None else "application/json", **(headers or {})}
    if token:
        h["Authorization"] = "Bearer " + token
    data = urllib.parse.urlencode(form).encode() if form is not None else None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(path if path.startswith("http") else BASE + path, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw[:200].decode("utf-8", "replace")}


def tool(name, args, token=None) -> dict:
    st, got = http("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}, token)
    res = (got or {}).get("result") or {} if isinstance(got, dict) else {}
    if res.get("isError"):
        return {"_error": (res.get("content") or [{}])[0].get("text", "")}
    return res.get("structuredContent") or {"_error": f"HTTP {st}: {str(got)[:200]}"}


def admin(body: dict) -> dict:
    return http("/api/project/operator", body, headers={"X-Knos-Admin": os.environ["KNOS_ADMIN_KEY"]}, timeout=600)[1]


def funded_project() -> tuple[str, str] | None:
    """The open autoresearch brief with locked money on its milestone; opened and funded by the operator when there is none."""
    def find():
        for p in http("/api/projects?take=100")[1].get("projects", []):
            m = (p.get("milestones") or [{}])[0]
            # an open milestone only: one another solver claimed, or one judged by a round a redeploy closed, cannot pay
            if p.get("solver_brief") == BRIEF and m.get("status") in (None, "", "open", "funded", "locked"):
                return p, m
        return None, None
    p, m = find()
    if p is None:
        got = admin({"action": "solver_open", "which": [BRIEF]})
        if not ok(got.get("projects"), "the operator opened the autoresearch brief (" + str(got.get("error") or "Ready") + ")"):
            return None
        p, m = got["projects"][0], got["projects"][0]["milestones"][0]
    if not m.get("locked_units"):
        got = admin({"action": "solver_fund", "project": p["id"], "units": 5})
        if not ok(got.get("status") == "locked", f"the operator funded it from the app's devnet test wallet ({got.get('status') or got.get('error')})"):
            return None
    return p["id"], m["key"]


def balance(owner: str) -> float:
    """Test units at `owner` on devnet: every SPL token account it owns (a fresh address holds only the test mint)."""
    req = {"jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
           "params": [owner, {"programId": TOKEN_PROGRAM}, {"encoding": "jsonParsed", "commitment": "confirmed"}]}
    got = http(RPC, req)[1]
    rows = (got.get("result") or {}).get("value") or []
    return sum(float(r["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0) for r in rows)


def winning_train(tasks: dict) -> str | None:
    """The baseline train.py with the change the round's README names (for example: features 'square', standardize True)."""
    rnd = (tasks.get("rounds") or [{}])[0].get("submit") or {}
    blob = rnd.get("baseline") or ""
    raw_url = blob.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/")
    st, src = http(raw_url, timeout=60)
    if st != 200 or not isinstance(src, str):
        return None
    what = rnd.get("what") or ""
    feat = re.search(r"features '(\w+)'", what)
    std = re.search(r"standardize (True|False)", what)
    out = src
    if feat:
        out = re.sub(r"'features': '\w+'", f"'features': '{feat.group(1)}'", out)
    if std:
        out = re.sub(r"'standardize': (True|False)", f"'standardize': {std.group(1)}", out)
    return out if out != src else None


def main() -> int:
    if not os.environ.get("KNOS_ADMIN_KEY"):
        print("FAIL set KNOS_ADMIN_KEY (the operator's key) in the environment")
        return 1
    from solders.keypair import Keypair
    payout = str(Keypair().pubkey())                     # the key pair is dropped: only the address is kept
    target = funded_project()
    if target is None:
        return 1
    pid, key = target
    owner = http("/api/auth/guest", {"label": "agent solver owner"})[1].get("token")
    ok(owner, "the owner has a guest session")
    st, made = http("/api/agent/keys", {"label": "outside solver", "max_claims": 1, "max_spend_units": 10, "days": 1,
                                        "payout_wallet": payout}, owner)
    if not ok(st == 200 and str(made.get("key", "")).startswith("knos_ak_"), f"the owner made agent key {made.get('id')} (shown once)"):
        return 1
    agent_key, kid = made.pop("key"), made["id"]
    secret = agent_key.split("_", 3)[3]
    before = balance(payout)

    # ---- from here on, ONLY the key ------------------------------------------------------------------------------------
    basic = base64.b64encode(f"{kid}:{secret}".encode()).decode()
    st, tok = http("/oauth/token", form={"grant_type": "client_credentials"}, headers={"Authorization": "Basic " + basic})
    access = tok.get("access_token") if isinstance(tok, dict) else None
    ok(st == 200 and access and tok.get("token_type") == "Bearer", f"OAuth 2.0 client credentials: a Bearer token, {tok.get('expires_in')} s")
    st, lst = http("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, access)
    names = {t["name"] for t in ((lst.get("result") or {}).get("tools") or [])} if isinstance(lst, dict) else set()
    ok({"knos_tasks", "knos_project_claim", "knos_milestone_submit"} <= names, f"tools/list: {len(names)} tools")
    tasks = tool("knos_tasks", {}, access)
    code = winning_train(tasks)
    ok(code, "the round's README names the change; the baseline train.py was read and changed")
    claimed = tool("knos_project_claim", {"project": pid, "milestone": key}, access)
    ok(claimed.get("wallet") == payout, f"claimed {pid}/{key}, paid at the key's payout wallet ({claimed.get('_error') or claimed.get('id')})")
    got = tool("knos_milestone_submit", {"project": pid, "milestone": key, "code": code or ""}, access)
    v = got.get("referee") or {}
    ok(v.get("pass"), f"the sealed referee: {v.get('decision')}, lift {v.get('lift')} over the baseline (needs {v.get('min_margin')})"
       + (f": {got['_error']}" if got.get("_error") else ""))
    # nobody acts from here: host 1 (the app) wakes host 2 by repository_dispatch when it holds a token, and the relay
    # workflow starts host 2 when it sees the open session (worker.yml); the 5-minute timer is the last resort
    end, started = time.monotonic() + 900, time.monotonic()
    status = got.get("milestone")
    while status != "released" and time.monotonic() < end and not got.get("_error"):
        time.sleep(10)                                   # the FROST referee hosts sign within minutes
        p = http(f"/api/project?id={pid}")[1]
        status = next((m.get("status") for m in p.get("milestones", []) if m.get("key") == key), status)
    ok(status == "released", f"the milestone is {status}, {time.monotonic() - started:.0f} s after the winning submission, 0 operator steps")
    after, end = balance(payout), time.monotonic() + 120
    while after <= before and time.monotonic() < end:
        time.sleep(5)
        after = balance(payout)
    ok(after > before, f"the payout address holds {after:g} test units on devnet (was {before:g}), read from {RPC}")

    # ---- the rule, and the revoke ------------------------------------------------------------------------------------
    no = tool("knos_project_open", {"template": "internal_tool", "title": "No credential"})
    ok("oauth-protected-resource" in no.get("_error", ""), "a write call with no credential is refused, naming the OAuth metadata")
    st, rev = http("/api/agent/keys/revoke", {"id": kid}, owner)
    ok(st == 200 and rev.get("state") == "revoked", "the owner revoked the key")
    for what, cred in (("its OAuth token", access), ("the key itself", agent_key)):
        got = tool("knos_project_open", {"template": "internal_tool", "title": "After revoke"}, cred)
        ok("revoked" in got.get("_error", ""), f"a write call with {what} is refused after the revoke")
    line = (f"PASS test_agent_solver: 0 operator steps, paid {after - before:g} test units on devnet" if not FAILS
            else f"FAIL test_agent_solver: {len(FAILS)} failed: {FAILS[:3]}")
    print(line, flush=True)
    world = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
    (world / "test_agent_solver.txt").write_text(line + "\n", encoding="utf-8")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
