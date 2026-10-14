"""python -m knos_wanted serve | probe | report "an idea" [--rival NAME ...] [--in PLACE] [--json]"""
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
    sub.add_parser("probe", help="which Qloo endpoints this key serves (status codes only)")
    r = sub.add_parser("report", help="print a Wanted Report")
    r.add_argument("idea")
    r.add_argument("--rival", action="append", default=[])
    r.add_argument("--in", dest="location")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        from .server import serve
        serve(a.host, a.port)
        return 0
    if a.cmd == "probe":
        from .probe import main as probe
        return probe()
    from .report import build
    rep = build(a.idea, a.rival, a.location)
    if a.json:
        print(json.dumps(rep, indent=1, default=str))
        return 0
    print(rep["label"])
    print(rep["framing"])
    print(f"Idea: {rep['idea']}\nLean: {rep['lean']['word']}  ({'; '.join(rep['lean']['why'])})")
    for sec in ("who", "where", "strength", "rising", "why", "compare"):
        print(f"- {sec}: {rep[sec]['status']}  {rep[sec].get('source', rep[sec].get('note', ''))}")
    print(f"Report hash: {rep['hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
