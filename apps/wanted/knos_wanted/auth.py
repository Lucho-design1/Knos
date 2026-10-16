"""Sign in: a passkey (WebAuthn), Google (only when GOOGLE_CLIENT_ID is set), or a guest label.

- Passkey: the browser makes a passkey (ES256, P-256); this server keeps its public key and the identity is derived from
  it ("passkey:<16 hex>"): a passkey wallet identity. Signing in = the passkey signs a fresh challenge, checked here
  (rpIdHash, user-present flag, challenge, origin, ECDSA signature). Needs the `cryptography` package; without it the
  passkey button says so. Knos holds no key for the user: devnet pre-orders are made by the app's demo wallet acting
  for the signed-in user (test money).
- Google: Google Identity Services gives the page an ID token; this server checks it with Google's tokeninfo endpoint
  (audience = GOOGLE_CLIENT_ID, issuer accounts.google.com, not expired). The button is shown only when GOOGLE_CLIENT_ID is set.
- Email: no email provider is configured, so an email typed here is only a display label: nothing is sent or verified.
A session is an HMAC-signed token (KNOS_WANTED_SESSION_SECRET, else a random secret per process) sent as a Bearer header.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SESSION_S = 12 * 3600
CHALLENGE_S = 300
_SECRET = (os.environ.get("KNOS_WANTED_SESSION_SECRET") or secrets.token_hex(32)).encode()
_challenges: dict[str, float] = {}
_lock = threading.Lock()
TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"


class AuthError(ValueError):
    pass


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s: str) -> bytes:
    s = str(s or "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def config() -> dict:
    email = bool(os.environ.get("RESEND_API_KEY") and os.environ.get("KNOS_WANTED_EMAIL_FROM"))
    return {"passkey": passkey_available(), "google_client_id": os.environ.get("GOOGLE_CLIENT_ID") or None,
            "orcid": bool(os.environ.get("ORCID_CLIENT_ID") and os.environ.get("ORCID_CLIENT_SECRET")),
            "email_provider": email,
            "email_note": ("a sign-in link is emailed to you" if email else
                           "no email provider is configured: an email typed here is only a display label; nothing is sent or verified")}


# ---- ORCID (OAuth 2 authorization code; production orcid.org or sandbox.orcid.org via ORCID_BASE) -------------------
def orcid_base() -> str:
    return (os.environ.get("ORCID_BASE") or "https://orcid.org").rstrip("/")


def orcid_authorize(redirect_uri: str) -> str:
    cid = os.environ.get("ORCID_CLIENT_ID")
    if not cid:
        raise AuthError("ORCID sign-in is not configured on this server (ORCID_CLIENT_ID, ORCID_CLIENT_SECRET)")
    state = challenge()
    return orcid_base() + "/oauth/authorize?" + urllib.parse.urlencode(
        {"client_id": cid, "response_type": "code", "scope": "/authenticate", "redirect_uri": redirect_uri, "state": state})


def orcid_callback(code: str, state: str, redirect_uri: str, opener=None) -> dict:
    cid, secret = os.environ.get("ORCID_CLIENT_ID"), os.environ.get("ORCID_CLIENT_SECRET")
    if not (cid and secret):
        raise AuthError("ORCID sign-in is not configured on this server")
    _take(state)
    data = urllib.parse.urlencode({"client_id": cid, "client_secret": secret, "grant_type": "authorization_code", "code": code,
                                   "redirect_uri": redirect_uri}).encode()
    req = urllib.request.Request(orcid_base() + "/oauth/token", data=data, headers={"Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=15) as r:
            got = json.loads(r.read(20_000))
    except urllib.error.HTTPError:
        raise AuthError("ORCID did not accept this sign-in") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise AuthError(f"ORCID could not be reached ({type(e).__name__})") from None
    oid = str(got.get("orcid") or "")
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", oid):
        raise AuthError("ORCID returned no iD")
    return issue("orcid:" + oid, "orcid", f"{got.get('name') or 'ORCID'} ({oid})")


# ---- email magic link (Resend) -------------------------------------------------------------------------------------
LINK_S = 15 * 60
_used_links: set[str] = set()


def email_link(email: str, base_url: str, opener=None) -> dict:
    key, sender = os.environ.get("RESEND_API_KEY"), os.environ.get("KNOS_WANTED_EMAIL_FROM")
    if not (key and sender):
        raise AuthError("email sign-in is not configured on this server (RESEND_API_KEY, KNOS_WANTED_EMAIL_FROM)")
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}", email):
        raise AuthError("type a valid email address")
    body = {"sub": "email:" + hashlib.sha256(email.encode()).hexdigest()[:16], "label": email, "exp": int(time.time() + LINK_S), "magic": True}
    raw = b64u(json.dumps(body, sort_keys=True).encode())
    tok = raw + "." + b64u(hmac.new(_SECRET, b"magic:" + raw.encode(), hashlib.sha256).digest())
    link = f"{base_url.rstrip('/')}/#magic={tok}"
    req = urllib.request.Request("https://api.resend.com/emails", method="POST",
                                 data=json.dumps({"from": sender, "to": [email], "subject": "Your Knos sign-in link",
                                                  "text": f"Sign in to Knos (valid 15 minutes):\n{link}\n\nIf you did not ask for this, ignore it."}).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=15) as r:
            r.read(2000)
    except (urllib.error.URLError, OSError) as e:
        raise AuthError(f"the sign-in email could not be sent ({type(e).__name__})") from None
    return {"sent": True, "to": email}


def email_verify(tok: str, now: float | None = None) -> dict:
    raw, _, sig = str(tok or "").partition(".")
    if not hmac.compare_digest(sig, b64u(hmac.new(_SECRET, b"magic:" + raw.encode(), hashlib.sha256).digest())):
        raise AuthError("this sign-in link is not valid")
    body = json.loads(unb64u(raw))
    if body.get("exp", 0) <= (now or time.time()):
        raise AuthError("this sign-in link has expired: ask for a new one")
    with _lock:
        if sig in _used_links:
            raise AuthError("this sign-in link was already used: ask for a new one")
        _used_links.add(sig)
    return issue(body["sub"], "email", body["label"])


# ---- sessions --------------------------------------------------------------------------------------------------------
def issue(sub: str, kind: str, label: str, now: float | None = None) -> dict:
    body = {"sub": sub, "kind": kind, "label": label[:80], "exp": int((now or time.time()) + SESSION_S)}
    raw = b64u(json.dumps(body, sort_keys=True).encode())
    tok = raw + "." + b64u(hmac.new(_SECRET, raw.encode(), hashlib.sha256).digest())
    return {"token": tok, **body}


def who(header: str | None, now: float | None = None) -> dict | None:
    if not header or not header.startswith("Bearer "):
        return None
    raw, _, sig = header[7:].strip().partition(".")
    if not hmac.compare_digest(sig, b64u(hmac.new(_SECRET, raw.encode(), hashlib.sha256).digest())):
        return None
    try:
        body = json.loads(unb64u(raw))
    except ValueError:
        return None
    return body if body.get("exp", 0) > (now or time.time()) else None


def guest(label: str) -> dict:
    label = " ".join(str(label or "").split())[:80] or "guest"
    return issue("guest:" + hashlib.sha256((label + secrets.token_hex(8)).encode()).hexdigest()[:16], "guest",
                 f"{label} (unverified label)")


# ---- passkeys --------------------------------------------------------------------------------------------------------
def passkey_available() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric import ec  # noqa: F401
        return True
    except ImportError:
        return False


def challenge() -> str:
    c = b64u(secrets.token_bytes(32))
    now = time.time()
    with _lock:
        for k in [k for k, t in _challenges.items() if now - t > CHALLENGE_S]:
            _challenges.pop(k)
        _challenges[c] = now
    return c


def _take(c: str) -> None:
    with _lock:
        t = _challenges.pop(c, None)
    if t is None or time.time() - t > CHALLENGE_S:
        raise AuthError("the sign-in challenge is unknown or expired: try again")


def _client_data(cdj_b64: str, want_type: str, origin: str) -> bytes:
    cdj = unb64u(cdj_b64)
    cd = json.loads(cdj)
    if cd.get("type") != want_type:
        raise AuthError("wrong WebAuthn ceremony")
    if cd.get("origin") != origin:
        raise AuthError("the passkey was made for another site")
    _take(cd.get("challenge", ""))
    return cdj


def _store() -> Path:
    d = Path(os.environ.get("KNOS_WANTED_STATE") or ".cache/state") / "passkeys"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cred_file(cred_id: str) -> Path:
    return _store() / (hashlib.sha256(unb64u(cred_id)).hexdigest() + ".pk")


def identity(spki: bytes) -> str:
    return "passkey:" + hashlib.sha256(spki).hexdigest()[:16]


def register(body: dict, origin: str, label: str = "") -> dict:
    """Keep a new passkey's public key (SPKI, ES256) after checking the creation ceremony's client data."""
    if not passkey_available():
        raise AuthError("passkeys need the cryptography package on this server")
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    _client_data(body.get("clientDataJSON", ""), "webauthn.create", origin)
    if body.get("alg") != -7:
        raise AuthError("only ES256 passkeys are accepted")
    spki = unb64u(body.get("publicKey", ""))
    key = load_der_public_key(spki)
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise AuthError("the passkey's public key is not P-256")
    cred = body.get("id", "")
    if not cred:
        raise AuthError("no credential id")
    _cred_file(cred).write_text(json.dumps({"spki": b64u(spki), "label": label[:80]}), encoding="utf-8")
    return issue(identity(spki), "passkey", label[:80] or identity(spki))


def login(body: dict, origin: str, rp_id: str) -> dict:
    """Check a passkey assertion over a fresh challenge."""
    if not passkey_available():
        raise AuthError("passkeys need the cryptography package on this server")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    f = _cred_file(body.get("id", ""))
    if not f.exists():
        raise AuthError("this passkey is not registered on this server")
    rec = json.loads(f.read_text(encoding="utf-8"))
    cdj = _client_data(body.get("clientDataJSON", ""), "webauthn.get", origin)
    auth = unb64u(body.get("authenticatorData", ""))
    if len(auth) < 37 or auth[:32] != hashlib.sha256(rp_id.encode()).digest():
        raise AuthError("the passkey answered for another site")
    if not auth[32] & 0x01:
        raise AuthError("the passkey did not confirm a user was present")
    spki = unb64u(rec["spki"])
    try:
        load_der_public_key(spki).verify(unb64u(body.get("signature", "")), auth + hashlib.sha256(cdj).digest(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise AuthError("the passkey's signature does not verify") from None
    return issue(identity(spki), "passkey", rec.get("label") or identity(spki))


# ---- Google ----------------------------------------------------------------------------------------------------------
def google(id_token: str, opener=None, now: float | None = None) -> dict:
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    if not cid:
        raise AuthError("Google sign-in is not configured on this server (GOOGLE_CLIENT_ID)")
    if not isinstance(id_token, str) or not 20 < len(id_token) < 4096:
        raise AuthError("no Google ID token")
    op = opener or urllib.request.urlopen
    try:
        with op(TOKENINFO + "?" + urllib.parse.urlencode({"id_token": id_token}), timeout=10) as r:
            info = json.loads(r.read(20_000))
    except urllib.error.HTTPError:
        raise AuthError("Google did not accept this ID token") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise AuthError(f"Google's tokeninfo could not be reached ({type(e).__name__})") from None
    if info.get("aud") != cid or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise AuthError("the ID token is for another app")
    if int(info.get("exp", 0)) <= (now or time.time()):
        raise AuthError("the ID token has expired")
    label = info.get("email") if str(info.get("email_verified")).lower() == "true" else info.get("name") or "Google user"
    return issue("google:" + str(info.get("sub")), "google", str(label))
