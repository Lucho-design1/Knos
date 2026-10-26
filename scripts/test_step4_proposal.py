"""test_step4_proposal, live and read only: key step 4 (the key admin moves to the upgrade vault) is proposed. program.yml passed on the commit that carries
the change and its release record (deploy/upgrade-step4/HASHES-v3.txt), and the upgrade multisig's proposal that
deploys that build is Approved by at least 2 of its 3 members, waiting on the multisig's time lock. Read from GitHub's
record of the run and from the proposal's Squads v4 account on devnet.

    python scripts/test_step4_proposal.py [commit] [proposal index]
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from solders.pubkey import Pubkey

ROOT = Path(__file__).resolve().parents[1]
IDS = json.loads((ROOT / "programs-v2" / "program_ids.json").read_text(encoding="utf-8"))
REPO, RPC = "drexthealpha/Knos", "https://api.devnet.solana.com"
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
STATUS = ("Draft", "Active", "Rejected", "Approved", "Executing", "Executed", "Cancelled")


def rpc(method: str, params: list):
    req = urllib.request.Request(RPC, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                 {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["result"]


def proposal(index: int) -> dict:
    """Squads v4 Proposal: disc 8 | multisig 32 | transaction_index u64 | status (u8 variant, i64 timestamp) | bump |
    approved Vec<Pubkey> | ..."""
    squads, ms = Pubkey.from_string(IDS["squads_program"]), Pubkey.from_string(IDS["upgrade_multisig"])
    pda = Pubkey.find_program_address([b"multisig", bytes(ms), b"transaction", index.to_bytes(8, "little"), b"proposal"], squads)[0]
    got = rpc("getAccountInfo", [str(pda), {"encoding": "base64"}])["value"]
    if not got:
        return {"address": str(pda), "status": None}
    d = base64.b64decode(got["data"][0])
    kind = d[48]
    i = 49 + (8 if STATUS[kind] in ("Draft", "Active", "Rejected", "Approved", "Executed", "Cancelled") else 0)
    ts = int.from_bytes(d[49:57], "little", signed=True) if i > 49 else None
    i += 1                                                    # bump
    n = int.from_bytes(d[i:i + 4], "little")
    return {"address": str(pda), "status": STATUS[kind], "at": ts, "approved": n}


def multisig_lock() -> int:
    d = base64.b64decode(rpc("getAccountInfo", [IDS["upgrade_multisig"], {"encoding": "base64"}])["value"]["data"][0])
    return int.from_bytes(d[74:78], "little")


def main(argv: list[str]) -> int:
    sha = argv[0] if argv else "0f3c47f98a008dacf14309eae056d8a20a15fec0"
    index = int(argv[1]) if len(argv) > 1 else 12
    runs = json.loads(subprocess.run(["gh", "run", "list", "-R", REPO, "-w", "program.yml", "-c", sha, "--json", "databaseId,conclusion,status"],
                                     capture_output=True, text=True, check=True).stdout or "[]")
    run = runs[0] if runs else {}
    p, lock = proposal(index), multisig_lock()
    until = dt.datetime.fromtimestamp(p["at"] + lock, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if p.get("at") else None
    lines = [f"program.yml on {sha[:8]}: run {run.get('databaseId')} {run.get('status')} {run.get('conclusion')}",
             f"proposal {index} ({p['address']}): {p['status']}, {p.get('approved')} approvals, time lock {lock} s, executable from {until}"]
    ok = run.get("conclusion") == "success" and p["status"] == "Approved" and (p.get("approved") or 0) >= 2 and lock >= 172_800
    lines.append(("PASS" if ok else "FAIL") + f" test_step4_proposal: program.yml {run.get('conclusion')} on {sha[:8]}, proposal {index} "
                 f"{p['status']} by {p.get('approved')} of 3, executable from {until}")
    print("\n".join(lines))
    (WORLD / "test_step4_proposal.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
