"""One referee HOST's signer: re-check the milestone itself, then FROST round 1 and round 2 for one session.

The nonces of round 1 live only in this process's memory and are used at most once: a host that is not chosen for
round 2, or whose run ends, drops them. Every message it posts carries its transport signature. Transports:
LocalClient (the app server's own share, in-process) and HttpClient (GitHub Actions and the PC, over HTTPS to the
app server). The PC daemon (`serve`) polls the app server for open sessions; GitHub Actions (cron every 5 minutes, or
workflow_dispatch) does the same once per run and adds a GitHub OIDC token to each post (knos.threshold.ghoidc).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from . import FrostError, auth, run
from .check import CheckFailed, milestone_digest


class LocalClient:
    def __init__(self, coordinator):
        self.c = coordinator

    def session(self, sid):
        from .session import public
        return public(self.c.get(sid))

    def pending(self):
        return self.c.pending()

    def commit(self, sid, pid, commitments, sig):
        return self.c.commit(sid, pid, commitments, sig)

    def share(self, sid, pid, share, sig):
        return self.c.share(sid, pid, share, sig)


class HttpClient:
    """The app server's referee endpoints (apps/wanted/knos_wanted/referee.py), HTTPS only (localhost for tests)."""

    def __init__(self, base: str, timeout: float = 20, host_token=None):
        """host_token: a callable giving a fresh identity token for every post (GitHub Actions: ghoidc.request_token)."""
        self.host_token = host_token
        if not (base.startswith("https://") or base.startswith(("http://127.0.0.1", "http://localhost"))):
            raise ValueError("the coordinator is reached over https")
        self.base, self.timeout = base.rstrip("/"), timeout

    def _call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json", "User-Agent": "knos-referee-frost"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - https (checked above)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                why = json.loads(e.read()).get("error")
            except ValueError:
                why = None
            raise FrostError(f"coordinator {path}: HTTP {e.code} {why or ''}".strip()) from None

    def session(self, sid):
        return self._call(f"/api/referee/session?id={sid}")

    def healthz(self) -> dict:
        """GET /healthz once: {"status": HTTP status or None, "ms": time taken, "error"?}. Never raises."""
        t0 = time.time()
        req = urllib.request.Request(self.base + "/healthz", headers={"User-Agent": "knos-referee-frost (healthz)"})
        try:
            with urllib.request.urlopen(req, timeout=max(self.timeout, 90)) as r:  # noqa: S310 - https (checked above)
                st, err = r.status, None
        except urllib.error.HTTPError as e:
            st, err = e.code, None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            st, err = None, type(e).__name__
        out = {"status": st, "ms": int((time.time() - t0) * 1000)}
        return out if err is None else {**out, "error": err}

    def pending(self):
        return self._call("/api/referee/pending").get("sessions", [])

    def commit(self, sid, pid, commitments, sig):
        return self._call("/api/referee/commit", self._proof({"session": sid, "id": pid, "commitments": commitments, "auth": sig}))

    def share(self, sid, pid, share, sig):
        return self._call("/api/referee/share", self._proof({"session": sid, "id": pid, "share": share, "auth": sig}))

    def _proof(self, body: dict) -> dict:
        if self.host_token is not None:
            body["oidc"] = self.host_token()            # fresh per post; never logged
        return body


def sign_session(share: dict, client, sid: str, led, *, fetcher=None, timeout: float = 900, poll: float = 2.0, on_verdict=None) -> dict:
    """Take part in one session. Returns {"id", "session", "outcome"}: shared | not chosen | refused: <why>.
    on_verdict(session, digest, evidence): called once this host's OWN check recomputed the session's digest, before
    any FROST round (the code referee's verdict file, knos.threshold.codeattest)."""
    pid = share["id"]
    s = client.session(sid)
    if s.get("group_key") != share["group_key"]:
        return {"id": pid, "session": sid, "outcome": "refused: another referee group"}
    try:
        kw = {"fetcher": fetcher} if fetcher else {}
        digest, _ev = milestone_digest(s["request"], share["group_key"], led, **kw)
    except CheckFailed as why:
        return {"id": pid, "session": sid, "outcome": f"refused: {why}"}
    if digest.hex() != s["digest"]:
        return {"id": pid, "session": sid, "outcome": "refused: the session's digest is not the one this host computed"}
    if on_verdict is not None:
        on_verdict(s, digest, _ev)
    if s.get("state") != "round1":
        return {"id": pid, "session": sid, "outcome": "not chosen (the signers were already fixed)"}
    one = run("commit", {"key_package": share["key_package"]})
    nonces = one.pop("nonces")
    try:
        client.commit(sid, pid, one["commitments"], auth(share, "commit", sid, one["commitments"]))
        end = time.time() + timeout
        while True:
            s = client.session(sid)
            if s.get("signing_package") is not None:
                break
            if time.time() > end:
                return {"id": pid, "session": sid, "outcome": "timed out waiting for a second referee (nonces dropped)"}
            time.sleep(poll)
        if pid not in s.get("signers", []):
            return {"id": pid, "session": sid, "outcome": "not chosen (two other referees sign)"}
        two = run("sign", {"key_package": share["key_package"], "nonces": nonces, "signing_package": s["signing_package"],
                           "message": digest.hex()})
    finally:
        nonces = None                                 # one use only, never written anywhere
    got = client.share(sid, pid, two["share"], auth(share, "share", sid, two["share"]))
    return {"id": pid, "session": sid, "outcome": "shared", "state": got.get("state")}


def serve(share: dict, client, led, *, every: float = 30.0, once: bool = False, on_verdict=None,
          healthz_every: float = 0.0, clock=time.time, sleep=time.sleep, log=print) -> None:
    """Host 3's daemon: poll the coordinator for open sessions and take part in each once. healthz_every > 0: also GET
    the app's /healthz that often (host 3 is the second pinger beside the GitHub Actions chain;
    .github/workflows/worker.yml) and log one JSON line per ping."""
    seen: set[str] = set()
    last_ping = None
    while True:
        if healthz_every > 0 and (last_ping is None or clock() - last_ping >= healthz_every):
            last_ping = clock()
            log(json.dumps({"id": share["id"], "healthz": client.healthz(), "at": int(last_ping)}), flush=True)
        try:
            for s in client.pending():
                if s["id"] not in seen and share["id"] not in s.get("committed", []):
                    seen.add(s["id"])
                    log(json.dumps(sign_session(share, client, s["id"], led, on_verdict=on_verdict)), flush=True)
        except (FrostError, OSError, ValueError) as why:
            # a refusal, or the network (a name that does not resolve, a reset, a timeout: URLError is an OSError) or a
            # garbled answer: one line, and the next poll tries again; the daemon never stops on one bad read
            log(json.dumps({"id": share["id"], "error": str(why)[:200]}), flush=True)
        if once:
            return
        sleep(every)
