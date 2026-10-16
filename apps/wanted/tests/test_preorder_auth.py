"""Milestone evidence checks, sign-in, and the new HTTP routes without escrow keys (no network, no chain)."""
import base64
import hashlib
import io
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from knos_wanted import auth, preorder, server
from knos_wanted.qloo_mcp import InProcess, Qloo
from knos_wanted.qloo_rest import Client

REC = {"claim_id": "knos-idea:" + "a" * 32}


def page(body: bytes):
    return lambda req, timeout=None: io.BytesIO(body)


def ok_host(host):
    return None


def test_evidence_must_contain_the_claim_id():
    ev, body = preorder.verify(REC, "https://maker.example/p", opener=page(b"<p>knos-idea:" + b"a" * 32 + b"</p>"), resolve=ok_host)
    assert ev["contains_claim_id"] and ev["sha256"] == hashlib.sha256(body).hexdigest()
    with pytest.raises(preorder.NotVerified, match="does not contain"):
        preorder.verify(REC, "https://maker.example/p", opener=page(b"nothing here"), resolve=ok_host)


@pytest.mark.parametrize("url", ["http://maker.example/p", "https://user:pw@maker.example/", "https://maker.example:8443/x", "ftp://x/y", ""])
def test_evidence_url_shape(url):
    with pytest.raises(preorder.NotVerified):
        preorder.fetch_evidence(url, opener=page(b"x"), resolve=ok_host)


def test_evidence_private_addresses_refused():
    with pytest.raises(preorder.NotVerified, match="private"):
        preorder.fetch_evidence("https://localhost/x", opener=page(b"x"))


def test_evidence_size_limit():
    with pytest.raises(preorder.NotVerified, match="larger"):
        preorder.fetch_evidence("https://maker.example/p", opener=page(b"x" * (preorder.MAX_EVIDENCE + 1)), resolve=ok_host)


def test_sessions_and_guest_label():
    s = auth.guest("ada@example.com")
    assert s["kind"] == "guest" and "unverified" in s["label"]
    assert auth.who("Bearer " + s["token"])["sub"] == s["sub"]
    assert auth.who("Bearer " + s["token"][:-2] + "xx") is None and auth.who(None) is None
    assert auth.who("Bearer " + s["token"], now=s["exp"] + 1) is None
    assert auth.config()["email_provider"] is False


def test_google_token_checked_against_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    info = {"aud": "cid.apps.googleusercontent.com", "iss": "accounts.google.com", "exp": "9999999999", "sub": "42",
            "email": "a@b.c", "email_verified": "true"}
    op = lambda url, timeout=None: io.BytesIO(json.dumps(info).encode())   # noqa: E731
    assert auth.google("x" * 40, opener=op)["sub"] == "google:42"
    info["aud"] = "other"
    with pytest.raises(auth.AuthError, match="another app"):
        auth.google("x" * 40, opener=op)
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    with pytest.raises(auth.AuthError, match="not configured"):
        auth.google("x" * 40, opener=op)


def test_passkey_register_and_login():
    ec = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ec")
    from cryptography.hazmat.primitives import hashes, serialization
    key = ec.generate_private_key(ec.SECP256R1())
    spki = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    origin, rp = "http://localhost:8080", "localhost"
    cid = auth.b64u(b"cred-1")

    def cd(kind):
        return auth.b64u(json.dumps({"type": kind, "challenge": auth.challenge(), "origin": origin}).encode())
    s = auth.register({"id": cid, "clientDataJSON": cd("webauthn.create"), "publicKey": auth.b64u(spki), "alg": -7}, origin, "Ada")
    assert s["sub"] == auth.identity(spki) and s["kind"] == "passkey"
    cdj = cd("webauthn.get")
    ad = hashlib.sha256(rp.encode()).digest() + b"\x05" + b"\x00\x00\x00\x01"
    sig = key.sign(ad + hashlib.sha256(base64.urlsafe_b64decode(cdj + "==")).digest(), ec.ECDSA(hashes.SHA256()))
    got = auth.login({"id": cid, "clientDataJSON": cdj, "authenticatorData": auth.b64u(ad), "signature": auth.b64u(sig)}, origin, rp)
    assert got["sub"] == s["sub"]
    with pytest.raises(auth.AuthError):          # the challenge was spent
        auth.login({"id": cid, "clientDataJSON": cdj, "authenticatorData": auth.b64u(ad), "signature": auth.b64u(sig)}, origin, rp)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOS_WANTED_REFEREE_KEYS", raising=False)
    state = server.State(Qloo(InProcess(), mode="mock", sleep=lambda s: None), Client(key="", base="https://example.test", folder=tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(base, path, body=None, token=None):
    h = {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})}
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_check_without_key_cannot_decide_and_preorder_is_gated(app):
    st, r = call(app, "/api/check", {"idea": "A smart water bottle that glows to remind you to drink", "place": "Lagos"})
    assert st == 200 and r["decision"]["verdict"] == "CANNOT_DECIDE" and r["decision"]["target_units"] is None
    assert call(app, "/api/check", {"idea": "mail me at jane@example.com about a bottle"})[0] == 400
    assert call(app, "/api/preorder", {"report": r["hash"], "units": 5})[0] == 401
    tok = call(app, "/api/auth/guest", {"label": "ada"})[1]["token"]
    st, e = call(app, "/api/preorder", {"report": r["hash"], "units": 5}, tok)
    assert st in (400, 503)
    st, s = call(app, "/api/status")
    assert s["preorders"]["available"] is False and s["preorders"]["why"] == "escrow unavailable on this server"
    assert s["qloo_rest"]["rest"] is False and s["qloo_rest"]["reason"] == "no Qloo API key on this server"
    assert call(app, "/api/report?hash=" + r["hash"])[1]["hash"] == r["hash"]


def test_preorder_refuses_reports_that_are_not_open():
    with pytest.raises((ValueError, preorder.Unavailable)):
        preorder.lock({"hash": "0" * 64, "decision": {"verdict": "REFUSE"}, "label": "LIVE"}, 5, "guest: x")


def test_a_maker_can_repost_evidence_ten_times_an_hour_per_commitment(app):
    tok = call(app, "/api/auth/guest", {"label": "maker"})[1]["token"]
    one, two = "1" * 44, "2" * 44
    codes = [call(app, "/api/milestone", {"commitment": one, "evidence_url": "https://x.example/"}, tok)[0] for _ in range(11)]
    assert codes[:10] == [400] * 10 and codes[10] == 429           # unknown commitment (400) until the per-commitment cap
    assert call(app, "/api/milestone", {"commitment": two, "evidence_url": "https://x.example/"}, tok)[0] == 400
