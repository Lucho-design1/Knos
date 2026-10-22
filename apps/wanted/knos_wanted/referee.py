"""The app server as referee host 1 and as the FROST COORDINATOR (knos.threshold), and its HTTPS endpoints.

On when KNOS_REFEREE_FROST_SHARE names this server's share file (a Render secret file) and the group record
(config/referee-frost.json, public) and knos-frost are present. Then every pre-order is a 1-of-1 PANEL order whose
one key is the FROST group key, and a milestone is released only when TWO of the three hosts sign:

    POST /api/milestone          (preorder.milestone) the server checks the evidence, opens a session, signs as host 1
                                 in the background; host 2 (.github/workflows/referee.yml, a cron every 5 minutes)
                                 and the PC daemon (host 3) poll /api/referee/pending
    GET  /api/referee/group      the group key, the hosts' transport keys (public)
    GET  /api/referee/pending    open sessions
    GET  /api/referee/session?id=
    POST /api/referee/commit     {session, id, commitments, auth[, oidc]}   a host's FROST round 1 (auth: its transport key)
    POST /api/referee/share      {session, id, share, auth[, oidc]}         a chosen host's round 2; the second one completes
                                 the signature and the server sends the release (knos.ideas.commit.release)

    POST /api/referee/attest     {session, verdict, oidc, bundle?, attestation_url?}   the CODE referee's attestation
                                 (knos.threshold.codeattest): referee.yml's job `attest` posts the verdict its own check
                                 wrote, a GitHub OIDC token whose audience names the verdict's sha256, and the Sigstore
                                 bundle actions/attest-build-provenance made for it. The server checks the token, has the
                                 DEPLOYED knos_oidc verify it on devnet (relay.verify_only), checks the bundle against
                                 Sigstore's public trust root, and records all of it on the session (`code_referee`).

Host 2's posts must also carry a GitHub Actions OIDC token (audience knos-referee) of referee.yml on main in
drexthealpha/Knos, verified against GitHub's JWKS (knos.threshold.ghoidc). No founder-made token is needed anywhere,
and no endpoint takes or returns a secret.
"""
from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_coord = None
_live: set[str] = set()                # sessions this process's host 1 is still signing (its nonces are in memory)


def host1_alive(sid: str) -> bool:
    """Is host 1 still waiting on this session here? Not after a restart or once it gave up: the session cannot complete."""
    with _lock:
        return sid in _live
GITHUB_HOST = ("polls: .github/workflows/referee.yml runs every 5 minutes (GitHub cron, may start late) and proves itself "
               "with its GitHub OIDC token")


def _share():
    from knos import threshold as T
    return T.load_share(os.environ["KNOS_REFEREE_FROST_SHARE"])


def enabled() -> bool:
    if not os.environ.get("KNOS_REFEREE_FROST_SHARE"):
        return False
    try:
        from knos import threshold as T
        T.binary()
        g = T.load_group()
        return _share()["group_key"] == g["group_key"]
    except Exception:  # noqa: BLE001 - never echo a share
        return False


def panel() -> tuple[int, list[str]]:
    from knos import threshold as T
    return 1, [T.load_group()["group_key"]]


def coordinator():
    global _coord
    with _lock:
        if _coord is None:
            from knos import threshold as T
            from knos.threshold.session import Coordinator

            from . import escrow
            from knos.threshold import ghoidc
            _coord = Coordinator(T.load_group(), escrow._state_dir() / "referee-sessions", on_signed=_released,
                                 host_auth={ghoidc.GH_HOST: ghoidc.verify})
        return _coord


def _released(s: dict) -> dict:
    """Two hosts signed: send the ONE group signature as the stage's verdict (the program checks it in the precompile)."""
    from knos.ideas import commit as C
    from knos.threshold import check

    from . import company, escrow, preorder, tasks
    order = s["meta"]["order"]
    if s["meta"].get("kind") == "project":                # a project milestone's order (knos_wanted.valley)
        from . import valley
        return valley.frost_released(s)
    if s["meta"].get("kind") == "prize":                  # a demo round's prize (knos_wanted.tasks)
        rec = tasks.load_prize(order)
        doc, led = rec["doc"], escrow.ledger()
        o = C._order(doc, "stage1", led)[1]
        v = check.verdict_record(doc, "stage1", {**s["meta"]["evidence"]}, bytes.fromhex(s["digest"]), s["signature"], s["group_key"], o.stamp)
        got = C.release(doc, "stage1", [v], preorder.relayer(), led)
        rec["status"] = got["status"] if got["status"] in ("released", "refunded") else "locked"
        rec["signatures"]["referee_group_pass"] = (got["sent"] or [{}])[0].get("signature")
        rec["referee_session"] = {"id": s["id"], "signers": s["signers"], "signature": s["signature"]}
        tasks.save_prize(rec)
        return {"status": rec["status"], "signatures": [x["signature"] for x in got["sent"]]}
    rec = preorder.load(order)
    doc, led = rec["doc"], escrow.ledger()
    o = C._order(doc, "stage1", led)[1]
    ev = {**s["meta"]["evidence"]}
    v = check.verdict_record(doc, "stage1", ev, bytes.fromhex(s["digest"]), s["signature"], s["group_key"], o.stamp)
    got = C.release(doc, "stage1", [v], preorder.relayer(), led)
    with preorder._lock:
        rec = preorder.load(order)
        rec["status"] = got["status"] if got["status"] in ("released", "refunded") else "locked"
        rec.setdefault("signatures", {})["referee_group_pass"] = (got["sent"] or [{}])[0].get("signature")
        rec["referee_session"] = {"id": s["id"], "signers": s["signers"], "signature": s["signature"]}
        if rec["status"] == "released":
            rec["release_record"] = company.record_release(rec["report"], order, [x["signature"] for x in got["sent"]], ev["evidence_hash"])
        preorder._save(rec)
    return {"status": rec["status"], "signatures": [x["signature"] for x in got["sent"]]}


def _verify_onchain(jwt: str) -> dict:
    """The DEPLOYED knos_oidc verifies the token on devnet; the relayer pays (its rent comes back when swept)."""
    from knos.settle.v2 import relay

    from . import escrow, preorder
    led, payer = escrow.ledger(), preorder.relayer()
    r = relay.verify_only(led, payer, jwt)
    if not r.get("ok") and "not on chain yet" in str(r.get("why")):
        relay.register_missing(led, payer)          # GitHub's genesis keys are anyone's to register (no attestation)
        r = relay.verify_only(led, payer, jwt)
    return r


def _check_bundle(bundle, sha: str, commit: str) -> dict:
    from knos.threshold import codeattest
    if bundle:
        return codeattest.verify_bundle(bundle, sha, commit=commit)
    last = None
    for b in codeattest.fetch_bundles(sha):
        try:
            return codeattest.verify_bundle(b, sha, commit=commit)
        except codeattest.AttestError as why:
            last = why
    raise last or codeattest.AttestError("GitHub holds no attestation for this verdict yet")


def attest(body: dict, *, coord=None, verify_token=None, onchain=None, check_bundle=None) -> dict:
    """The code referee's attestation of one session: verdict + OIDC token (+ Sigstore bundle). Idempotent per verdict."""
    from knos.threshold import codeattest, ghoidc
    c = coord or coordinator()
    sid = str(body.get("session", ""))
    s = c.get(sid)
    rec, sha = codeattest.check_verdict(body.get("verdict") or "", s)
    have = s.get("code_referee") or {}
    if have.get("verdict_sha256") == sha and (have.get("onchain") or {}).get("ok") and (have.get("attestation") or {}).get("ok"):
        return have
    claims = (verify_token or ghoidc.verify)(str(body.get("oidc") or ""), audience=codeattest.AUD_PREFIX + sha)
    codeattest.check_claims(claims, rec, sha)
    out = {"verdict_sha256": sha, "verdict": rec, "run": codeattest.run_url(rec), "commit": rec["github"]["sha"],
           "token": {k: claims.get(k) for k in ("repository", "repository_id", "workflow_ref", "sha", "run_id", "run_attempt", "event_name", "aud", "exp")}}
    if (have.get("onchain") or {}).get("ok") and have.get("verdict_sha256") == sha:
        out["onchain"] = have["onchain"]
    else:
        r = (onchain or _verify_onchain)(str(body["oidc"]))
        out["onchain"] = {"ok": bool(r.get("ok")), "program": "knos_oidc", "signatures": list(r.get("sigs") or []), "account": r.get("account"),
                          "already": bool(r.get("already")), **({} if r.get("ok") else {"why": str(r.get("why"))[:200]})}
    url = str(body.get("attestation_url") or "")
    try:
        att = (check_bundle or _check_bundle)(body.get("bundle"), sha, rec["github"]["sha"])
        out["attestation"] = {**att, "rekor": codeattest.rekor_url(att.get("log_index")),
                              "url": url if url.startswith(f"https://github.com/{codeattest.REPOSITORY}/attestations/") else None}
    except codeattest.AttestError as why:
        out["attestation"] = {"ok": False, "why": str(why)[:200]}
    c.annotate(sid, "code_referee", out)
    return out


def trust(session_id: str | None) -> dict | None:
    """What a milestone page shows for its referee session: the code referee's run, the knos_oidc verification
    transaction, the Sigstore attestation, and the FROST release. None without a session or a FROST host."""
    if not session_id or not enabled():
        return None
    try:
        s = coordinator().get(session_id)
    except ValueError:
        return None
    cr = s.get("code_referee") or {}
    res = s.get("result") or {}
    return {"session": s["id"], "state": s.get("state"), "signers": s.get("signers"), "run": cr.get("run"), "commit": cr.get("commit"),
            "verdict_sha256": cr.get("verdict_sha256"), "oidc_verify": (cr.get("onchain") or {}).get("signatures", [])[-1:] or None,
            "oidc_account": (cr.get("onchain") or {}).get("account"), "attestation": cr.get("attestation"),
            "frost_signature": s.get("signature"), "release": (res.get("signatures") or [None])[0]}


def start(rec: dict, url: str, led, kind: str = "preorder") -> dict:
    """Open a signing session for a verified milestone; host 1 signs in the background; hosts 2 and 3 poll for it."""
    from knos.threshold import check, participant
    share, c = _share(), coordinator()
    req = check.request(rec["doc"], "stage1", url)
    digest, ev = check.milestone_digest(req, share["group_key"], led)
    s = c.open(req, digest, meta={"order": rec["order"], "kind": kind, "evidence": {k: ev[k] for k in ("met", "evidence_hash", "oracle")}})
    from knos.threshold.session import SESSION_LIFE_S

    def host1():
        try:                                       # as long as the session lives: GitHub may start host 2's cron late
            participant.sign_session(share, participant.LocalClient(c), s["id"], led, timeout=SESSION_LIFE_S)
        finally:
            with _lock:
                _live.discard(s["id"])
    with _lock:
        _live.add(s["id"])
    threading.Thread(target=host1, daemon=True).start()
    return {"session": s["id"], "digest": s["digest"], "github": GITHUB_HOST, "evidence_hash": ev["evidence_hash"],
            "needs": "2 of 3 referee hosts (this server, GitHub Actions, the founder's PC) sign one FROST signature"}


def get(path: str, qs: dict) -> tuple[int, dict]:
    if not enabled():
        return 404, {"error": "this server is not a FROST referee host"}
    from knos import threshold as T
    from knos.threshold.session import public
    if path == "/api/referee/group":
        g = T.load_group()
        return 200, {k: g[k] for k in ("group_key", "min", "max", "hosts", "panel", "keygen", "scheme")}
    if path == "/api/referee/pending":
        return 200, {"sessions": coordinator().pending()}
    if path == "/api/referee/session":
        try:
            return 200, public(coordinator().get((qs.get("id") or [""])[0]))
        except ValueError as why:
            return 404, {"error": str(why)}
    return 404, {"error": "not found"}


def post(path: str, body: dict) -> tuple[int, dict]:
    if not enabled():
        return 404, {"error": "this server is not a FROST referee host"}
    from knos.threshold import FrostError
    c = coordinator()
    try:
        if path == "/api/referee/commit":
            return 200, c.commit(str(body.get("session", "")), int(body.get("id", 0)), body.get("commitments") or {}, str(body.get("auth", "")),
                                 body.get("oidc"))
        if path == "/api/referee/attest":
            return 200, attest(body)
        if path == "/api/referee/share":
            return 200, c.share(str(body.get("session", "")), int(body.get("id", 0)), body.get("share") or {}, str(body.get("auth", "")),
                                body.get("oidc"))
    except PermissionError as why:
        return 401, {"error": str(why)[:200]}
    except (ValueError, TypeError, FrostError) as why:
        return 400, {"error": str(why)[:200]}
    return 404, {"error": "not found"}
