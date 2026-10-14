"""The receipt `knos verify` writes: canonical JSON, its sha256 digest, and an ed25519 signature by this machine's
verify key.

What the signature means, and what it does not: it binds the receipt's words to one key, so nobody can change a
count after the fact without the check failing. It is NOT an attestation that the tests ran as described: a local
run is self-reported by the machine that ran it (`runner.attestation` says so). A receipt with hidden tests run by
Knos Gate in a pinned workflow is Gate's receipt (knos.receipt2), not this one.

The key: $KNOS_VERIFY_KEY, else <knos home>/verify-key.json (made on first use, mode 0600, never printed).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

KIND, VERSION = "knos-verify-receipt", 1
REQUIRED = ("kind", "v", "repo", "commit", "base", "spec_hash", "tests", "hidden", "cheat_checks", "ai_policy",
            "ai_disclosure", "runner", "verdict", "reasons", "made_at")
VERDICTS = ("pass", "fail", "refused")


def canonical(receipt: dict) -> bytes:
    """The bytes that are hashed and signed: the receipt without `signature`, keys sorted, no spaces, UTF-8."""
    body = {k: v for k, v in receipt.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(receipt: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(receipt)).hexdigest()


def key_path() -> Path:
    given = os.environ.get("KNOS_VERIFY_KEY")
    if given:
        return Path(given).expanduser()
    from .. import paths
    return paths.home() / "verify-key.json"


def _keypair(create: bool = True):
    from solders.keypair import Keypair
    path = key_path()
    if path.is_file():
        return Keypair.from_bytes(bytes(json.loads(path.read_text(encoding="utf-8"))))
    if not create:
        return None
    kp = Keypair()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(list(bytes(kp))))
    return kp


def signer() -> str:
    """The public key receipts from this machine are signed with (made on first use)."""
    return str(_keypair().pubkey())


def sign(receipt: dict) -> dict:
    """The receipt with `signature` {alg, key, sig, digest} added."""
    kp = _keypair()
    body = {k: v for k, v in receipt.items() if k != "signature"}
    sig = kp.sign_message(canonical(body))
    return {**body, "signature": {"alg": "ed25519", "key": str(kp.pubkey()), "sig": str(sig), "digest": digest(body)}}


def problems(receipt) -> list[str]:
    """Why this is not a well-formed, correctly signed receipt; [] when it is. Checks the shape, the digest and the
    signature against the key the receipt names (compare that key with the one you expect: `knos verify --key`)."""
    if not isinstance(receipt, dict):
        return ["a receipt is a JSON object"]
    out = [f"missing {k}" for k in REQUIRED if k not in receipt]
    if receipt.get("kind") != KIND or receipt.get("v") != VERSION:
        out.append(f"kind/v must be {KIND}/{VERSION}")
    if receipt.get("verdict") not in VERDICTS:
        out.append(f"verdict must be one of {', '.join(VERDICTS)}")
    hidden = receipt.get("hidden")
    if isinstance(hidden, dict) and set(hidden) - {"count", "mode", "note"}:
        out.append("hidden may carry only count, mode and note (never test names or contents)")
    sig = receipt.get("signature")
    if not isinstance(sig, dict):
        return out + ["unsigned"]
    if sig.get("digest") != digest(receipt):
        out.append("digest does not match the receipt")
    try:
        from solders.pubkey import Pubkey
        from solders.signature import Signature
        ok = Signature.from_string(str(sig.get("sig"))).verify(Pubkey.from_string(str(sig.get("key"))), canonical(receipt))
    except (ValueError, TypeError):
        ok = False
    if not ok:
        out.append("signature does not verify")
    return out


def markdown(receipt: dict) -> str:
    """The block an agent pastes into the pull request's description: verdict, counts, cheat checks, the AI-use line,
    and the digest a reader checks the attached receipt against. Never test output, never hidden test names."""
    t, h = receipt["tests"], receipt["hidden"]
    runs = t.get("runs") or []
    counts = ", ".join(f"run {i + 1}: exit {r.get('exit')}" + (f", {r['passed']} passed, {r['failed']} failed" if r.get("passed") is not None else "")
                       for i, r in enumerate(runs)) or "not run"
    fired = [c for c in receipt["cheat_checks"]["findings"] if c["severity"] == "refuse"]
    rerun = {True: "re-run matched", False: "re-run did NOT match", None: "no re-run"}[t.get("rerun_match")]
    lines = [
        f"**Knos verify: {receipt['verdict']}** at `{receipt['commit'][:12]}` against `{receipt['base'][:12]}`",
        f"- Tests: `{t.get('command') or 'none run'}`; {counts}; {rerun}",
        f"- Hidden tests: {h['mode']} (count {h['count']})",
        f"- Cheat checks ({receipt['cheat_checks']['engine']}): " + ("none fired" if not fired else ", ".join(sorted({c['rule'] for c in fired}))),
        f"- AI policy: {receipt['ai_policy']['stance']}" + (f" ({receipt['ai_policy']['file']})" if receipt["ai_policy"].get("file") else ""),
        f"- {receipt['ai_disclosure']}",
        f"- Runner: {receipt['runner']['attestation']}",
    ]
    sig = receipt.get("signature")
    if isinstance(sig, dict):
        lines.append(f"- Receipt digest `{sig['digest']}`, signed by `{sig['key']}`")
    return "\n".join(lines) + "\n"
