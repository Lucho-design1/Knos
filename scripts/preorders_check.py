"""test_preorders_from_city: the check a launch milestone names (apps/wanted metros.brief). It passes when the
milestone holds at least its brief's pre-order target of locked pre-orders, each an order account that exists on
devnet under the app's payment program. The city is the brief's term: devnet cannot see where a wallet's owner lives,
so this counts the pre-orders and says so. Standard library only (GitHub Actions runs it as the job of that name).

    python scripts/preorders_check.py <project id> [app address]
"""
from __future__ import annotations

import json
import sys
import urllib.request

RPC = "https://api.devnet.solana.com"
PROGRAM = "FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4"      # knos-pay 0.3.34, the app's live program


def get(url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "knos-preorders-check"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main(pid: str, app: str = "https://knos.onrender.com") -> int:
    p = get(f"{app}/api/project?id={pid}")
    m = next(x for x in p["milestones"] if (x.get("verifier") or {}).get("check") == "test_preorders_from_city")
    launch = ((p.get("versions") or [{}])[-1].get("brief") or {}).get("launch") or {}
    target = int(launch.get("target") or 0)
    locked = [o for o in m.get("orders") or [] if o.get("status") == "locked"]
    on_chain, funders = 0, set()
    for o in locked:
        acct = (get(RPC, {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo", "params": [o["order"], {"encoding": "base64", "commitment": "confirmed"}]})
                .get("result") or {}).get("value")
        if acct and acct.get("owner") == PROGRAM:
            on_chain += 1
            funders.add(o.get("funder"))
    print(f"project {pid}, milestone {m['key']}: target {target} pre-orders from {launch.get('city')}; "
          f"{len(locked)} locked, {on_chain} confirmed as order accounts of {PROGRAM} on devnet, from {len(funders)} wallets")
    return 0 if target > 0 and on_chain >= target else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
