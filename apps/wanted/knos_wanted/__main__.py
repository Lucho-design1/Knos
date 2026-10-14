"""python -m knos_wanted serve | status | maker "an idea" [--rival NAME ...] [--in PLACE] [--pick first] | anchor

`maker --pick first` runs the whole MAKER flow from a terminal, confirming the FIRST candidate for every question
(for demos and smoke tests; a real maker confirms each match in the page)."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m knos_wanted")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the web app (HOST, PORT)")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    sub.add_parser("status", help="Qloo MCP readiness (live or MOCK), tools listed, contract checksum: no Qloo call")
    m = sub.add_parser("maker", help="a demand report from a terminal")
    m.add_argument("idea")
    m.add_argument("--rival", action="append", default=[])
    m.add_argument("--variant", action="append", default=[])
    m.add_argument("--in", dest="location")
    m.add_argument("--pick", choices=["first"], required=True, help="confirm the first candidate of every question")
    m.add_argument("--json", action="store_true")
    m.add_argument("--record", action="store_true", help="write the report to the Knos Record")
    sub.add_parser("anchor", help="anchor every unanchored Record line on devnet (KNOS_WANTED_DEVNET_KEYPAIR signs)")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        from .server import serve
        serve(a.host, a.port)
        return 0
    if a.cmd == "anchor":
        from .company import anchor
        print(json.dumps(anchor(), indent=1))
        return 0
    from .qloo_mcp import Qloo
    q = Qloo()
    try:
        if a.cmd == "status":
            st = q.status()
            print(json.dumps({k: st[k] for k in ("mode", "label", "reason", "transport", "server", "tools", "ready",
                                                 "contract_version", "contract_checksum")}, indent=1))
            return 0
        from . import company, demand
        sess = demand.start(q, a.idea, a.rival, a.location, a.variant or None)
        choices = {qn["key"]: qn["candidates"][0]["id"] for qn in sess["questions"] if qn["candidates"]}
        rep = demand.confirm(q, sess, choices)
        if a.record:
            rep["record"] = company.record_report(rep)
        if a.json:
            print(json.dumps(rep, indent=1, default=str))
            return 0
        print(rep["label"])
        print(f"{rep['framing']} Results describe {rep['aggregate']}.")
        print(f"Idea: {rep['idea']}\nLean (Knos's rule): {rep['lean']['word']}  ({'; '.join(rep['lean']['why'])})")
        for t in rep["trail"]:
            print(f"- {t['step']:<22} {t['tool'] or '(confirmed)':<28} {t['status']:<12} {t['why']}")
        print(f"Report sha256: {rep['hash']}")
        if a.record:
            print(f"Record: {json.dumps(rep['record'])}")
        return 0
    finally:
        q.close()


if __name__ == "__main__":
    sys.exit(main())
