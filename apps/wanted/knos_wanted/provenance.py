"""Evidence provenance: in-toto/DSSE attestations of milestone evidence, and C2PA-signed photos and videos.

in-toto   Every released attempt gets an in-toto Statement v1 (https://in-toto.io/Statement/v1) whose subjects are the
          maker's result page and the independent check (sha256 of the bytes the server fetched), predicate type
          https://knos.onrender.com/attestation/milestone/v1, wrapped in a DSSE envelope signed with this server's
          ed25519 attestation key (KNOS_ATTEST_KEY, a file; else one made once in the state folder). Key-based, not
          Sigstore keyless: keyless needs an interactive OIDC sign-in or a CI identity, so CI runs carry the GitHub-OIDC
          keyless attestation instead (.github/workflows/attest.yml) and this server signs with its own published key
          (GET /api/attest/key). Anyone verifies an envelope offline with that key (verify_envelope).
C2PA      A maker's photo or video of physical evidence is signed with a C2PA manifest (c2pa-python) carrying the
          milestone's claim id: POST /api/evidence/c2pa signs an uploaded JPEG/PNG/MP4 and returns it; /api/evidence/c2pa/verify
          reads a manifest back. The signing certificate is a Knos TEST certificate made here (TEST CERTIFICATE: not
          on the C2PA trust list), so a verifier shows the claim and the signature but not a trusted signer.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path

from . import escrow

PAYLOAD_TYPE = "application/vnd.in-toto+json"
STATEMENT = "https://in-toto.io/Statement/v1"
PREDICATE = "https://knos.onrender.com/attestation/milestone/v1"
TEST_CERT_LABEL = "Knos TEST certificate (devnet evidence; not on the C2PA trust list)"
MAX_MEDIA = 4_000_000
MEDIA = {"image/jpeg", "image/png", "video/mp4"}


# ---- in-toto / DSSE --------------------------------------------------------------------------------------------------
def _key_file() -> Path:
    v = os.environ.get("KNOS_ATTEST_KEY")
    return Path(v).expanduser() if v else escrow._state_dir() / "attest-ed25519.pem"


def _key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    f = _key_file()
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        k = Ed25519PrivateKey.generate()
        f.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.chmod(f, 0o600)
    return serialization.load_pem_private_key(f.read_bytes(), password=None)


def public_key() -> dict:
    from cryptography.hazmat.primitives import serialization
    pub = _key().public_key()
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    pem = pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return {"keyid": hashlib.sha256(raw).hexdigest(), "scheme": "ed25519", "public_key_pem": pem, "public_key_hex": raw.hex()}


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE pre-authentication encoding (https://github.com/secure-systems-lab/dsse/blob/master/protocol.md)."""
    t = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


def statement(project: dict, milestone: dict, attempt: dict, orders: list[dict]) -> dict:
    subj = [{"name": f"{role}:{attempt[role]['url']}", "digest": {"sha256": attempt[role]["sha256"]}}
            for role in ("result", "check") if attempt.get(role)]
    return {"_type": STATEMENT, "subject": subj, "predicateType": PREDICATE,
            "predicate": {"project": project["id"], "title": project["title"], "milestone": milestone["key"], "name": milestone["name"],
                          "attempt": attempt["id"], "maker": attempt.get("maker"), "checker": (attempt.get("check") or {}).get("by"),
                          "status": attempt.get("status"), "rule": "result + independent check, two people, two sites",
                          "orders": [{"order": o.get("order"), "status": o.get("status"), "signatures": o.get("signatures")} for o in orders],
                          "cluster": "devnet", "money": "devnet test units"}}


def sign_envelope(stmt: dict) -> dict:
    payload = json.dumps(stmt, sort_keys=True, separators=(",", ":")).encode()
    sig = _key().sign(pae(PAYLOAD_TYPE, payload))
    return {"payloadType": PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
            "signatures": [{"keyid": public_key()["keyid"], "sig": base64.b64encode(sig).decode()}]}


def verify_envelope(env: dict, public_key_hex: str) -> dict:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    payload = base64.b64decode(env["payload"])
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    for s in env.get("signatures", []):
        try:
            pub.verify(base64.b64decode(s["sig"]), pae(env["payloadType"], payload))
            st = json.loads(payload)
            return {"valid": True, "keyid": s.get("keyid"), "statement": st}
        except (InvalidSignature, ValueError, KeyError):
            continue
    return {"valid": False}


def attest(pid: str, key: str, attempt_id: str) -> dict:
    from . import valley
    p = valley.project(pid)
    m = valley._milestone(p, key)
    a = next((x for x in m["attempts"] if x["id"] == attempt_id), None)
    if a is None or not a.get("result"):
        raise valley.Refused("attempt: one with a posted result")
    orders = [o for o in (valley._safe_order(x) for x in m["fundings"]) if o]
    env = sign_envelope(statement(p, m, a, orders))
    return {"envelope": env, "key": public_key(), "verify": "DSSE over the in-toto Statement v1; check with GET /api/attest/key"}


# ---- C2PA ------------------------------------------------------------------------------------------------------------
def _test_cert() -> tuple[bytes, bytes]:
    """A test CA and an ES256 signing certificate for C2PA (made once, kept in the state folder)."""
    d = escrow._state_dir() / "c2pa-test"
    cert_f, key_f = d / "chain.pem", d / "signer.key"
    if cert_f.exists() and key_f.exists():
        return cert_f.read_bytes(), key_f.read_bytes()
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Knos (TEST)"),
                         x509.NameAttribute(NameOID.COMMON_NAME, "Knos TEST evidence CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False,
                                       key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Knos (TEST)"),
                                     x509.NameAttribute(NameOID.COMMON_NAME, "Knos TEST evidence signer")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    d.mkdir(parents=True, exist_ok=True)
    chain = leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    cert_f.write_bytes(chain)
    key_f.write_bytes(pem)
    os.chmod(key_f, 0o600)
    return chain, pem


def c2pa_available() -> bool:
    try:
        import c2pa  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def c2pa_sign(data: bytes, mime: str, claim_id: str, title: str = "milestone evidence") -> dict:
    """Sign a photo or video with a C2PA manifest naming the milestone's claim id. Returns the signed file (base64)."""
    import c2pa
    if mime not in MEDIA:
        raise ValueError(f"media: one of {', '.join(sorted(MEDIA))}")
    if not data or len(data) > MAX_MEDIA:
        raise ValueError(f"media: 1 byte to {MAX_MEDIA:,} bytes")
    if not isinstance(claim_id, str) or not 4 <= len(claim_id) <= 120:
        raise ValueError("claim_id: the milestone's claim id")
    cert, key = _test_cert()
    manifest = {"claim_generator_info": [{"name": "Knos", "version": "0.4"}], "title": title[:80], "format": mime,
                "assertions": [{"label": "c2pa.actions", "data": {"actions": [{"action": "c2pa.created",
                                                                                 "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture"}]}},
                               {"label": "org.knos.milestone", "data": {"claim_id": claim_id, "cluster": "devnet",
                                                                        "certificate": TEST_CERT_LABEL}}]}
    info = c2pa.C2paSignerInfo(b"es256", cert, key, None)
    signer = c2pa.Signer.from_info(info)
    src, dst = io.BytesIO(data), io.BytesIO()
    with c2pa.Builder(json.dumps(manifest)) as b:
        b.sign(signer, mime, src, dst)
    out = dst.getvalue()
    return {"signed": base64.b64encode(out).decode(), "sha256": hashlib.sha256(out).hexdigest(), "bytes": len(out),
            "manifest": c2pa_read(out, mime), "certificate": TEST_CERT_LABEL}


def c2pa_read(data: bytes, mime: str) -> dict:
    import c2pa
    with c2pa.Reader(mime, io.BytesIO(data)) as r:
        store = json.loads(r.json())
    active = store.get("manifests", {}).get(store.get("active_manifest") or "", {})
    knos = next((a.get("data") for a in active.get("assertions", []) if a.get("label") == "org.knos.milestone"), None)
    return {"active_manifest": store.get("active_manifest"), "claim_generator": (active.get("claim_generator_info") or [{}])[0].get("name"),
            "knos": knos, "signature": active.get("signature_info"),
            "validation": [{"code": v.get("code"), "explanation": v.get("explanation")} for v in (store.get("validation_status") or [])][:12],
            "certificate": TEST_CERT_LABEL}
