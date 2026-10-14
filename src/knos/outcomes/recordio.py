"""Knos Record entries for outcomes: one per measurement, one per cheat caught, one per payment or refund.

Written through Knos Record's own API (`knos.record.append`, agent RECORD; NOTES "RECORD API"), which keeps the
append-only, hash-chained journal and its Sibyl copy and refuses anything that looks like a secret. When that package
is not installed (a CI runner with only this package vendored, say) the same entry goes to a JSONL file of its own,
`outcome-record.jsonl`, in the same directory; `knos record` does not read that file, and RECORD's journal is never
written here.

Every payload is public and redacted: hashes, the domain, pass or fail, the cheat's category, amounts in the mint's
smallest units, devnet signatures, and `synthetic` when the data are made up. No item ids, no rows, no names but the
public GitHub ids already in the spec, no token, no key.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

FALLBACK = "outcome-record.jsonl"
DOMAIN = "outcomes"
_SECRETISH = re.compile(r"(eyJ[A-Za-z0-9_-]{10,}\.|-----BEGIN|ghp_|gho_|ghs_|github_pat_|\"secret\"|\bpassword\b|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,})")


def root_dir(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    if os.environ.get("KNOS_RECORD_DIR"):
        return Path(os.environ["KNOS_RECORD_DIR"])
    return Path(os.environ.get("KNOS_HOME", Path.home() / ".knos")) / "record"


def safe(payload: dict) -> None:
    """Refuses a payload with anything that reads as a token, a key, a PEM block or an e-mail address."""
    text = json.dumps(payload, sort_keys=True)
    if _SECRETISH.search(text):
        raise ValueError("a record entry must hold no token, key or personal data")
    for v in _walk(payload):
        if isinstance(v, list) and len(v) == 64 and all(isinstance(x, int) for x in v):
            raise ValueError("a record entry must hold no key bytes")


def _walk(v: Any):
    yield v
    if isinstance(v, dict):
        for x in v.values():
            yield from _walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk(x)


def append(kind: str, payload: dict, *, claim: str | None = None, root: str | Path | None = None) -> dict:
    """One entry, through knos.record when it is installed, else the fallback file. Returns the entry."""
    safe(payload)
    try:
        from knos import record  # type: ignore[attr-defined]
        add = record.append
    except (ImportError, AttributeError):
        add = None
    if add is not None:
        return add(kind, payload, claim=claim, domain=DOMAIN, root=root)
    where = root_dir(root)
    where.mkdir(parents=True, exist_ok=True)
    path = where / FALLBACK
    prev = ""
    if path.is_file():
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        prev = json.loads(lines[-1])["hash"] if lines else ""
        seq = len(lines)
    else:
        seq = 0
    entry = {"v": 1, "seq": seq, "ts": int(time.time()), "kind": kind, "claim": claim, "domain": DOMAIN, "payload": payload, "prev": prev}
    entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
    return entry


def measurement(result: dict, *, root: str | Path | None = None) -> list[dict]:
    """The entries of one measurement: one `verification` (pass or fail, per tier) and one `cheat` per finding."""
    base = {"spec_hash": result["spec_hash"], "domain": DOMAIN, "synthetic": bool(result.get("synthetic")),
            "cluster": result.get("cluster", "devnet"), "result_hash": result.get("result_hash", "")}
    out = [append("verification", {**base, "passed": bool(result["passed"]), "refused": bool(result.get("refused")),
                                   "tiers": [{"name": t["name"], "passed": t["passed"]} for t in result.get("tiers", [])],
                                   "lift": result.get("lift"), "lower_bound": result.get("lower_bound"), "cheat": None},
                  claim=result["spec_hash"], root=root)]
    for f in result.get("findings", []):
        out.append(append("cheat", {**base, "passed": False, "cheat": f["category"], "rule": f["rule"]}, claim=result["spec_hash"], root=root))
    return out


def money(kind: str, *, spec_hash: str, tier: str, amount: int, mint: str, tx: str, synthetic: bool, root: str | Path | None = None) -> dict:
    """A `payout` or a `refund` of one tier's order, with its devnet signature."""
    if kind not in ("payout", "refund", "funding"):
        raise ValueError(kind)
    return append(kind, {"spec_hash": spec_hash, "domain": DOMAIN, "tier": tier, "amount": int(amount), "mint": mint, "tx": tx,
                         "cluster": "devnet", "synthetic": bool(synthetic), "cheat": None}, claim=spec_hash, root=root)
