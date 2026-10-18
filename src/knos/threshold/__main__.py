"""python -m knos.threshold <command>: Knos's FROST referee hosts.

    dkg-local --out DIR [--group PATH]     run the DKG as three separate processes on this machine (one per host);
                                           writes DIR/share-render.json, share-github.json, share-pc.json (0600) and
                                           the PUBLIC group record (default config/referee-frost.json)
    dkg-party --id N --relay DIR --run ID --out FILE    one DKG party (what dkg-local starts; or one per host)
    sign-session --session ID [--coordinator URL] [--github-oidc]   one signing session (GitHub Actions: share from
                                           $KNOS_REFEREE_FROST_SHARE, the JSON itself)
    serve [--coordinator URL] [--every S] [--once] [--github-oidc]  take part in every open session (the PC daemon;
                                           GitHub Actions with --once --github-oidc: each post carries the job's OIDC
                                           token, audience knos-referee)
    info                                   the group key and hosts (public)
Never prints a share.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from . import GROUP_FILE, HOSTS, load_group, load_share

COORDINATOR = "https://knos.onrender.com"


def _share(arg: str | None) -> dict:
    src = arg or os.environ.get("KNOS_REFEREE_FROST_SHARE")
    if not src:
        sys.exit("give --share FILE or set KNOS_REFEREE_FROST_SHARE")
    return load_share(src)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m knos.threshold")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("dkg-local")
    a.add_argument("--out", required=True)
    a.add_argument("--group", default=str(GROUP_FILE))
    b = sub.add_parser("dkg-party")
    b.add_argument("--id", type=int, required=True)
    b.add_argument("--relay", required=True)
    b.add_argument("--run", required=True)
    b.add_argument("--out", required=True)
    for name in ("sign-session", "serve"):
        c = sub.add_parser(name)
        c.add_argument("--share")
        c.add_argument("--coordinator", default=os.environ.get("KNOS_REFEREE_COORDINATOR", COORDINATOR))
        if name == "sign-session":
            c.add_argument("--session", required=True)
        else:
            c.add_argument("--every", type=float, default=30.0)
            c.add_argument("--once", action="store_true")
        c.add_argument("--github-oidc", action="store_true", help="add this GitHub Actions job's OIDC token to every post")
    sub.add_parser("info")
    ns = ap.parse_args(argv)

    if ns.cmd == "dkg-party":
        from .dkg import DirRelay, party
        print(json.dumps(party(ns.id, DirRelay(ns.relay), ns.run, ns.out)))
        return 0
    if ns.cmd == "dkg-local":
        from .dkg import DirRelay, group_record
        out = Path(ns.out).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        os.chmod(out, 0o700)
        relay, run_id = out / ".relay", uuid.uuid4().hex
        procs = [subprocess.Popen([sys.executable, "-m", "knos.threshold", "dkg-party", "--id", str(i), "--relay", str(relay),
                                   "--run", run_id, "--out", str(out / f"share-{HOSTS[i]}.json")], stdout=subprocess.PIPE)
                 for i in sorted(HOSTS)]
        res = [json.loads(p.communicate(timeout=900)[0] or b"{}") for p in procs]
        if any(p.returncode for p in procs):
            sys.exit("the DKG failed in one party; no group record written")
        rec = group_record(DirRelay(relay), run_id)
        shutil.rmtree(relay)                            # public packages and ciphertexts only; not kept
        Path(ns.group).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({"group_key": rec["group_key"], "parties": [r.get("id") for r in res], "group_record": ns.group}))
        return 0
    if ns.cmd == "info":
        g = load_group()
        print(json.dumps({k: g[k] for k in ("group_key", "min", "max", "hosts", "panel", "keygen")}, indent=1))
        return 0
    from knos import chain
    from .participant import HttpClient, serve, sign_session
    token = None
    if ns.github_oidc:
        from .ghoidc import request_token
        token = request_token
    share, client, led = _share(ns.share), HttpClient(ns.coordinator, host_token=token), chain.ledger()
    if ns.cmd == "sign-session":
        got = sign_session(share, client, ns.session, led)
        print(json.dumps(got))
        return 0 if got["outcome"] in ("shared",) or got["outcome"].startswith("not chosen") else 1
    serve(share, client, led, every=ns.every, once=ns.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
