"""UNUSED: a Google Confidential Space attestation token verifier. Nothing in Knos calls `verify`; Knos runs no Confidential
Space referee and claims none. The code referee is attested by GitHub Actions + knos_oidc on chain + Sigstore instead
(knos.threshold.codeattest). Kept only because it is tested (tests/test_threshold_frost.py), and because ghoidc uses
its RS256 helpers (`_b64`, `_rsa_verify`).

`verify(token, ...)` checks an attestation token the way Google documents it (Confidential Space token claims and
"Validate the token": RS256, keys from the issuer's discovery document's jwks_uri) and Knos's pins:

    iss       https://confidentialcomputing.googleapis.com
    aud       the audience Knos asked for (knos.proof.issuers.proof_audience, or a referee session's)
    exp/nbf   in time (60 s skew)
    swname    CONFIDENTIAL_SPACE; hwmodel one of the Confidential VM technologies; dbgstat disabled-since-boot
    support   submods.confidential_space.support_attributes holds STABLE (a production Confidential Space image)
    image     submods.container.image_digest == the pinned container image digest
    project   submods.gce.project_id == the pinned Google Cloud project

Nothing here makes or fakes a token: a real one comes only from a Confidential Space VM. DEPLOYMENT STATUS: BLOCKED,
outside Knos: Confidential Space runs on Compute Engine Confidential VMs, which need a Google Cloud project with a
billing account; Knos has none (see docs/reference/REFEREE_FROST.md). The verifier is tested with tokens signed by a
test RSA key, labelled as such.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.request

ISSUER = "https://confidentialcomputing.googleapis.com"
DISCOVERY = ISSUER + "/.well-known/openid-configuration"
# Google's token-claims reference (read 17 Oct 2026) lists GCP_AMD_SEV, GCP_AMD_SEV_ES, GCP_SHIELDED_VM, GCP_INTEL_TDX;
# a Shielded VM is not a Confidential VM, so it is refused.
HW = ("GCP_AMD_SEV", "GCP_AMD_SEV_ES", "GCP_INTEL_TDX")
SKEW_S = 60
BLOCKED = ("Confidential Space needs a Google Cloud project with a billing account (Compute Engine Confidential VMs); "
           "Knos has none. Outside blocker: a Google Cloud billing account.")


class AttestationError(ValueError):
    pass


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jwks(fetch=None) -> dict:
    """Google's signing keys for Confidential Space tokens: discovery document -> jwks_uri -> keys (live fetch)."""
    get = fetch or (lambda u: json.loads(urllib.request.urlopen(u, timeout=10).read()))  # noqa: S310 - fixed https URLs
    disc = get(DISCOVERY)
    if disc.get("issuer") != ISSUER:
        raise AttestationError("the discovery document names another issuer")
    return get(disc["jwks_uri"])


def _rsa_verify(jwk: dict, signed: bytes, sig: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    if jwk.get("kty") != "RSA":
        return False
    pub = rsa.RSAPublicNumbers(int.from_bytes(_b64(jwk["e"]), "big"), int.from_bytes(_b64(jwk["n"]), "big")).public_key()
    try:
        pub.verify(sig, signed, padding.PKCS1v15(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def verify(token: str, *, audience: str, image_digest: str, project_id: str, keys: dict | None = None,
           now: float | None = None, nonce: str | None = None) -> dict:
    """The token's claims when every check passes; AttestationError naming the first one that fails."""
    try:
        h64, p64, s64 = token.split(".")
        head, claims, sig = json.loads(_b64(h64)), json.loads(_b64(p64)), _b64(s64)
    except (ValueError, AttributeError):
        raise AttestationError("not a JWT") from None
    if head.get("alg") != "RS256":
        raise AttestationError("the token is not RS256")
    keyset = keys if keys is not None else jwks()
    jwk = next((k for k in keyset.get("keys", []) if k.get("kid") == head.get("kid")), None)
    if jwk is None or not _rsa_verify(jwk, f"{h64}.{p64}".encode(), sig):
        raise AttestationError("the token's signature does not verify with the issuer's published key")
    t = time.time() if now is None else now
    if claims.get("iss") != ISSUER:
        raise AttestationError("iss: not Confidential Space")
    aud = claims.get("aud")
    if (aud if isinstance(aud, list) else [aud]) != [audience]:
        raise AttestationError("aud: not the audience Knos asked for")
    if not (claims.get("exp", 0) + SKEW_S > t >= claims.get("nbf", claims.get("iat", 0)) - SKEW_S):
        raise AttestationError("the token is expired or not yet valid")
    if claims.get("swname") != "CONFIDENTIAL_SPACE" or claims.get("hwmodel") not in HW:
        raise AttestationError("swname/hwmodel: not a Confidential Space VM")
    if claims.get("dbgstat") != "disabled-since-boot":
        raise AttestationError("dbgstat: a debug image (its operator can read its memory)")
    sub = claims.get("submods") or {}
    if "STABLE" not in ((sub.get("confidential_space") or {}).get("support_attributes") or []):
        raise AttestationError("support_attributes: not a supported production Confidential Space image")
    want = image_digest if image_digest.startswith("sha256:") else "sha256:" + image_digest
    if (sub.get("container") or {}).get("image_digest") != want:
        raise AttestationError("image_digest: not the pinned container image")
    if (sub.get("gce") or {}).get("project_id") != project_id:
        raise AttestationError("project_id: not the pinned Google Cloud project")
    if nonce is not None and nonce not in (claims.get("eat_nonce") or []):
        raise AttestationError("eat_nonce: not this request's nonce")
    return claims


def status() -> dict:
    return {"verifier": "built (knos.threshold.attest.verify)", "deployment": "BLOCKED", "blocker": BLOCKED}
