"""Knos Receipt (receipt2): what a pull request carries after Knos Gate (or the author's own public-tests run) judged it.

    {"receipt": BODY, "signature": {"alg": "ed25519", "key": <base58 public key>, "sig": <base58 64 bytes>}}

BODY (type knos.pr-receipt, version 1) holds: the repository, pull request, head and base commits; `mode`
("hidden" or "public-tests-only", said in words in `scope_note`); `spec_hash` (the seal of the hidden tests);
`tests` (counts only: never a test's name, message or output); `cheat_checks` (the library, the rules it ran, every
finding by rule, category and path); `runner` (where it ran, as the run's own environment reports it, and the run's
address); `rerun` (whether the hidden suite was run a second time and agreed); `verdict` ("passed" or "refused") with
its `rule`; `issued_at`; `issuer` (a name and the public key); `links.install` (turn on Knos Gate).

The signature is over `canonical(BODY)` (keys sorted, no white space, UTF-8). `verify` needs only the standard library
(knos.receipt2.ed25519), so anyone can check a receipt offline. `known_issuer` says whether the key is one this
package lists (issuers.json): a valid signature by an unknown key proves only that the key's holder signed it.
`secrets_in` refuses to build or accept a receipt that carries anything shaped like a token, key or address of mail."""
from __future__ import annotations

import hashlib
import json
import re
import time
from importlib import resources
from pathlib import Path

from . import ed25519

TYPE, VERSION = "knos.pr-receipt", 1
INSTALL = "https://github.com/drexthealpha/Knos/blob/main/docs/reference/PR_GATE.md#install"
_SECRET = [re.compile(p) for p in (
    r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.", r"\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]",
    r"xox[abposr]-[A-Za-z0-9-]{10,}", r"AKIA[0-9A-Z]{16}", r"sk-[A-Za-z0-9]{20,}",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")]
MODES = ("hidden", "public-tests-only")


def canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(body: dict) -> str:
    return hashlib.sha256(canonical(body)).hexdigest()


def secrets_in(obj) -> list[str]:
    text = json.dumps(obj, ensure_ascii=False)
    return [p.pattern for p in _SECRET if p.search(text)]


def _counts(c: dict | None) -> dict | None:
    if c is None:
        return None
    return {k: int(c.get(k, 0)) for k in ("total", "passed", "failed", "errors", "skipped")}


def runner_from_env(env: dict) -> dict:
    """Where the run happened, as GitHub Actions' environment says it. Not signed by GitHub in this receipt."""
    server, repo, run = env.get("GITHUB_SERVER_URL", "https://github.com"), env.get("GITHUB_REPOSITORY", ""), env.get("GITHUB_RUN_ID", "")
    if not run:
        return {"kind": "local", "attested": False, "note": "run on the author's own machine: nothing but this signature vouches for it"}
    return {"kind": "github-actions", "attested": False, "run_id": run, "run_attempt": env.get("GITHUB_RUN_ATTEMPT", ""),
            "workflow_ref": env.get("GITHUB_WORKFLOW_REF", ""), "workflow_sha": env.get("GITHUB_WORKFLOW_SHA", ""),
            "runner_environment": env.get("RUNNER_ENVIRONMENT", ""), "os": env.get("RUNNER_OS", ""),
            "run_url": f"{server}/{repo}/actions/runs/{run}" + (f"/attempts/{env['GITHUB_RUN_ATTEMPT']}" if env.get("GITHUB_RUN_ATTEMPT") else ""),
            "note": "as reported by the run's own environment; open run_url to see GitHub's record of it"}


def build(verdict: dict, *, issuer_name: str, issuer_key: str, runner: dict, rerun: dict | None = None,
          rules_run: list[str] | None = None, issued_at: int | None = None) -> dict:
    """The receipt BODY from a Gate verdict (knos.gate.verdict.decide)."""
    mode = verdict.get("mode") if verdict.get("mode") in MODES else "public-tests-only"
    body = {
        "type": TYPE, "version": VERSION,
        "repository": verdict["repo"], "pull_request": int(verdict["pr"]), "head": verdict["head"], "base": verdict.get("base", ""),
        "mode": mode,
        "scope_note": "judged against sealed hidden tests the author could not read" if mode == "hidden"
                      else "PUBLIC TESTS ONLY: this repository has no sealed hidden tests, so only its own public tests ran",
        "spec_hash": verdict.get("spec_hash") or "",
        "tests": {"hidden": _counts(verdict.get("hidden")), "public": _counts(verdict.get("public")),
                  "contents": "never included: counts only"},
        "cheat_checks": {"library": verdict.get("library", ""), "rules_run": sorted(rules_run or []),
                         "findings": [{k: f.get(k, "") for k in ("rule", "category", "path")} for f in verdict.get("findings", [])],
                         "passed": not any(f.get("severity", "refuse") == "refuse" for f in verdict.get("findings", []))},
        "runner": runner,
        "rerun": rerun or {"ran": False, "agrees": None},
        "verdict": "passed" if verdict["passed"] else "refused", "rule": verdict.get("rule", ""),
        "issued_at": int(time.time() if issued_at is None else issued_at),
        "issuer": {"name": issuer_name, "key": issuer_key},
        "links": {"install": INSTALL, "run": runner.get("run_url", "")},
    }
    bad = secrets_in(body)
    if bad:
        raise ValueError(f"the receipt would carry something shaped like a secret ({bad[0]}); nothing was signed")
    return body


def keypair_from_file(path: Path | str):
    from solders.keypair import Keypair
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Keypair.from_bytes(bytes(raw))


def keygen(path: Path | str) -> str:
    """A new signing key for receipts, written as a 64-number JSON array (mode 600). Returns its public key."""
    import os

    from solders.keypair import Keypair
    kp = Keypair()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(list(bytes(kp))))
    return str(kp.pubkey())


def sign(body: dict, keypair) -> dict:
    if body.get("issuer", {}).get("key") != str(keypair.pubkey()):
        raise ValueError("the receipt names another issuer key than the one signing it")
    sig = keypair.sign_message(canonical(body))
    return {"receipt": body, "signature": {"alg": "ed25519", "key": str(keypair.pubkey()), "sig": str(sig)}}


def known_issuers() -> list[dict]:
    return json.loads(resources.files(__package__).joinpath("issuers.json").read_text(encoding="utf-8"))["issuers"]


def known_issuer(key: str) -> dict | None:
    return next((i for i in known_issuers() if i["key"] == key), None)


def verify(envelope: dict) -> dict:
    """{"valid": bool, "why": str, "issuer": known issuer or None, "digest": sha256 of the body}. Standard library only."""
    try:
        body, sig = envelope["receipt"], envelope["signature"]
        if sig.get("alg") != "ed25519":
            return {"valid": False, "why": f"unknown signature algorithm {sig.get('alg')!r}", "issuer": None, "digest": ""}
        if body.get("type") != TYPE or body.get("version") != VERSION:
            return {"valid": False, "why": "not a knos.pr-receipt version 1", "issuer": None, "digest": ""}
        if body.get("issuer", {}).get("key") != sig.get("key"):
            return {"valid": False, "why": "the body names another issuer key than the signature", "issuer": None, "digest": ""}
        key, raw = ed25519.b58decode(sig["key"]), ed25519.b58decode(sig["sig"])
    except (KeyError, TypeError, AttributeError, ValueError) as why:
        return {"valid": False, "why": f"not a receipt envelope ({why})", "issuer": None, "digest": ""}
    d = digest(body)
    if secrets_in(body):
        return {"valid": False, "why": "the receipt carries something shaped like a secret", "issuer": None, "digest": d}
    if not ed25519.verify(key, canonical(body), raw):
        return {"valid": False, "why": "the signature does not match the receipt (it was changed, or signed by another key)", "issuer": None, "digest": d}
    who = known_issuer(sig["key"])
    return {"valid": True, "why": "signature valid" + ("" if who else "; the key is not one Knos lists, so it shows only that its holder signed"),
            "issuer": who, "digest": d}


def rerun_agrees(first: dict, second: dict) -> bool:
    """Two runs of the hidden suite agree when they pass or fail alike AND count the same: total, passed, failed and
    errors (Gate's counts are numbers: 3 of 3 then 2 of 3 is a disagreement)."""
    from ..gate import sealed
    keys = ("total", "passed", "failed", "errors")
    return sealed.passed(first) == sealed.passed(second) and all(int(first.get(k, -1)) == int(second.get(k, -1)) for k in keys)
