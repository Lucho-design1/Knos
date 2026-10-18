"""The FROST signing COORDINATOR (runs on the app server; holds no secret). One session = one verdict digest.

    open(request, digest)   a release request every referee re-checks itself (check.milestone_digest)
    commit(sid, pid, c, a)  a host's round-1 commitments (a: its transport signature); at t of them the coordinator
                            fixes the signing package (those t signers, the digest) and round 2 opens
    share(sid, pid, s, a)   a chosen signer's round-2 signature share; with all t, the coordinator aggregates
                            (frost::aggregate verifies every share against its verifying share) and checks the one
                            Ed25519 signature under the group key; then `on_signed(session)` sends the release

`host_auth` {host id: verify(token)} adds a host proof on top of the transport signature: the app server requires a
GitHub Actions OIDC token from host 2 (knos.threshold.ghoidc), so host 2's posts need no founder-made token.

A session is never re-opened with other signers: a stalled one is abandoned and a new one opened (fresh nonces). The
coordinator cannot sign: it has no share, and a forged or altered share fails aggregation.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from . import FrostError, auth_ok, run

ROUND1, ROUND2, SIGNED, FAILED = "round1", "round2", "signed", "failed"
SESSION_LIFE_S = 3600


class Coordinator:
    def __init__(self, group: dict, store: str | Path, on_signed=None, host_auth: dict | None = None):
        self.group, self.store = group, Path(store)
        self.host_auth = dict(host_auth or {})
        self.store.mkdir(parents=True, exist_ok=True)
        self.on_signed = on_signed
        self._lock = threading.Lock()

    # -- storage -------------------------------------------------------------------------------------------------
    def _f(self, sid: str) -> Path:
        if not (isinstance(sid, str) and len(sid) == 32 and all(c in "0123456789abcdef" for c in sid)):
            raise ValueError("session: 32 hex characters")
        return self.store / f"{sid}.json"

    def _save(self, s: dict) -> None:
        f = self._f(s["id"])
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
        os.replace(tmp, f)

    def get(self, sid: str) -> dict:
        f = self._f(sid)
        if not f.exists():
            raise ValueError("unknown referee session")
        return json.loads(f.read_text(encoding="utf-8"))

    def pending(self) -> list[dict]:
        out, now = [], time.time()
        for f in sorted(self.store.glob("*.json")):
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if s.get("state") in (ROUND1, ROUND2) and now - s.get("opened", 0) < SESSION_LIFE_S:
                out.append(public(s))
        return out

    def _host_ok(self, pid: int, token) -> None:
        check = self.host_auth.get(pid)
        if check is None:
            return
        if not token:
            raise PermissionError(f"referee {pid}: this host's posts need its identity token")
        check(str(token))                              # raises PermissionError naming the failed check

    # -- protocol ------------------------------------------------------------------------------------------------
    def open(self, request: dict, digest: bytes, meta: dict | None = None) -> dict:
        sid = hashlib.sha256(digest + os.urandom(16)).hexdigest()[:32]
        s = {"id": sid, "state": ROUND1, "digest": digest.hex(), "request": request, "meta": meta or {},
             "group_key": self.group["group_key"], "min": self.group["min"], "commitments": {}, "signers": [],
             "signing_package": None, "shares": {}, "signature": None, "opened": time.time(), "log": []}
        with self._lock:
            self._save(s)
        return public(s)

    def commit(self, sid: str, pid: int, commitments: dict, sig: str, host_token: str | None = None) -> dict:
        pid = int(pid)
        with self._lock:
            s = self.get(sid)
            if not auth_ok(self.group, pid, "commit", sid, commitments, sig):
                raise PermissionError(f"referee {pid}: the commitments are not signed by its transport key")
            self._host_ok(pid, host_token)
            if s["state"] != ROUND1:
                return public(s)                         # late: the signers are chosen already
            if str(pid) in s["commitments"]:
                raise ValueError(f"referee {pid} committed already in this session")
            s["commitments"][str(pid)] = commitments
            s["log"].append({"at": time.time(), "event": "commit", "id": pid})
            if len(s["commitments"]) >= s["min"]:
                chosen = dict(list(s["commitments"].items())[: s["min"]])
                s["signers"] = sorted(int(k) for k in chosen)
                s["signing_package"] = run("package", {"commitments": chosen, "message": s["digest"]})["signing_package"]
                s["state"] = ROUND2
            self._save(s)
            return public(s)

    def share(self, sid: str, pid: int, share: dict, sig: str, host_token: str | None = None) -> dict:
        pid = int(pid)
        with self._lock:
            s = self.get(sid)
            if not auth_ok(self.group, pid, "share", sid, share, sig):
                raise PermissionError(f"referee {pid}: the share is not signed by its transport key")
            self._host_ok(pid, host_token)
            if s["state"] != ROUND2 or pid not in s["signers"]:
                raise ValueError(f"referee {pid} is not a signer of this session's round 2")
            s["shares"][str(pid)] = share
            s["log"].append({"at": time.time(), "event": "share", "id": pid})
            done = None
            if all(str(i) in s["shares"] for i in s["signers"]):
                try:
                    agg = run("aggregate", {"signing_package": s["signing_package"], "shares": s["shares"], "public": self.group["public"]})
                except FrostError as why:
                    s["state"], s["error"] = FAILED, str(why)[:300]
                else:
                    ok = run("verify", {"group_key": self.group["group_key_hex"], "message": s["digest"], "signature": agg["signature"]})["ok"]
                    if not ok:
                        s["state"], s["error"] = FAILED, "the aggregated signature does not verify under the group key"
                    else:
                        s["state"], s["signature"] = SIGNED, agg["signature"]
                        done = s
            self._save(s)
        if done is not None and self.on_signed is not None:
            result = self.on_signed(done)
            with self._lock:
                s = self.get(sid)
                s["result"] = result
                self._save(s)
        return public(self.get(sid))


def public(s: dict) -> dict:
    """What any host may read: no secret is ever in a session (commitments, packages and shares are public)."""
    return {k: s.get(k) for k in ("id", "state", "digest", "request", "group_key", "min", "signers", "signing_package",
                                  "signature", "error", "result", "opened")} | {"committed": sorted(int(k) for k in s.get("commitments", {})),
                                                                                "shared": sorted(int(k) for k in s.get("shares", {}))}
