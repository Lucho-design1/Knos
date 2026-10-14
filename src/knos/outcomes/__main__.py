"""`python -m knos.outcomes measure|audiences|check-audience ...`: what the reusable workflow runs, with the standard
library alone (no typer, no solders), so the measuring job installs nothing but the measuring code itself.

    python -m knos.outcomes measure outcome.yaml --lock outcome.lock.json --repo . --out result.json
    python -m knos.outcomes audiences result.json            the passed tiers' pay audiences, as one JSON line
    python -m knos.outcomes check-audience outcome.yaml outcome.lock.json AUDIENCE
                                                             exit 0 only for an audience of a tier order the lock lists,
                                                             the spec's seller, and that tier's terms hash
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

AUD = re.compile(r"^knos3:pay:([1-9A-HJ-NP-Za-km-z]{32,44}):([0-9a-f]{40}):([0-9a-f]{64}):([01]):(\d{1,19}):(\d{1,19})\.10000\.([1-9A-HJ-NP-Za-km-z]{32,44})$")


def check_audience(spec: dict, lock: dict, audience: str) -> list[str]:
    from .spec import spec_hash, terms_hash
    m = AUD.match(audience)
    if not m:
        return ["not a knos3:pay audience with one payee"]
    order, _head, terms, mode, pr, payee, address = m.groups()
    out = []
    if lock.get("spec_hash") != spec_hash(spec):
        out.append("the lock is not this spec's")
    tiers = {o["address"]: int(o["tier"]) for o in lock.get("orders", [])}
    if order not in tiers:
        out.append("the order is not one of the lock's tiers")
    elif terms != terms_hash(spec, tiers[order]).hex():
        out.append("the terms hash is not that tier's")
    seller = spec["parties"]["seller"]
    if int(payee) != int(seller["id"]) or address != seller["address"]:
        out.append("the payee is not the spec's seller")
    if int(mode) != int(lock.get("mode", 0)) or int(pr) != int(spec["escrow"]["issue"]):
        out.append("the mode or the issue is not the spec's")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m knos.outcomes")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("spec", type=Path)
    m.add_argument("--lock", type=Path, required=True)
    m.add_argument("--repo", type=Path)
    m.add_argument("--data", type=Path)
    m.add_argument("--out", type=Path)
    m.add_argument("--now", type=int)
    m.add_argument("--record", action="store_true")
    a = sub.add_parser("audiences")
    a.add_argument("result", type=Path)
    c = sub.add_parser("check-audience")
    c.add_argument("spec", type=Path)
    c.add_argument("lock", type=Path)
    c.add_argument("audience")
    args = p.parse_args(argv)
    if args.cmd == "measure":
        from . import measure, recordio
        from .data import DataError
        from .spec import SpecError
        try:
            rc = measure.main_measure(args.spec, args.lock, args.repo, args.out, args.now, args.data)
        except (SpecError, DataError) as why:
            print(f"refused: {why}", file=sys.stderr)
            return 2
        if args.record and args.out:
            recordio.measurement(json.loads(args.out.read_text(encoding="utf-8")))
        return rc
    if args.cmd == "audiences":
        doc = json.loads(args.result.read_text(encoding="utf-8"))
        print(json.dumps([t["audience"] for t in doc.get("tiers", []) if t.get("passed") and t.get("audience")], separators=(",", ":")))
        return 0
    from .spec import load
    bad = check_audience(load(args.spec), json.loads(args.lock.read_text(encoding="utf-8")), args.audience)
    for b in bad:
        print(b, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
