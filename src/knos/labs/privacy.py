"""Private by default: lab results and buyer data stay with the buyer. Knos Record (public) gets only

    hashes      of the spec, of the evidence (results + raw files), of the order id, and a SALTED reference to the lab
    timing      when it was ordered, when results came, the turnaround in seconds
    verdicts    the LAB verdict and the OUTCOME verdict (PASS / FAIL / VOID), and the release transactions

and never the results, the sequences or protocol, the buyer, the price, or the lab's name. A lab's name is replaced
by sha256(salt + lab): the buyer keeps the salt, so nobody can count a lab's failures from the public record (a lab's
failure rate is never published without its consent). With the buyer's opt-in (`publish`) the results' summary goes
in too; with the lab's consent (`lab_consents`) its name does.
"""
from __future__ import annotations

import secrets

from ..record.journal import redaction_problems
from .base import sha256_hex
from .verdicts import Verdict

PRIVATE_KEYS = ("runs", "qc", "protocol", "sequences", "buyer", "price", "amount_usd", "lab", "claim", "raw", "files")


def new_salt() -> str:
    return secrets.token_hex(16)


def lab_ref(lab: str, salt: str) -> str:
    """The lab, unlinkable without the buyer's salt (different salt per order: no two orders link either)."""
    return sha256_hex(f"knos-lab:{salt}:{lab}")


def public_record(*, order_id: str, field: str, lab: str, salt: str, spec_hash: str, lab_v: Verdict, outcome_v: Verdict | None,
                  ordered_at: str, results_at: str, turnaround_s: int, releases: list[dict] | None = None,
                  publish: dict | None = None, lab_consents: bool = False, synthetic: bool = False) -> dict:
    """The one payload a lab order may put in the public Knos Record."""
    out = {"lab_order": sha256_hex(f"knos-order:{order_id}"), "field": field,
           "lab_ref": lab if lab_consents else lab_ref(lab, salt), "lab_named": bool(lab_consents),
           "spec_hash": spec_hash, "evidence_hash": lab_v.evidence_hash,
           "lab_verdict": lab_v.verdict, "outcome_verdict": outcome_v.verdict if outcome_v else None,
           "ordered_at": ordered_at, "results_at": results_at, "turnaround_s": int(turnaround_s),
           "releases": [{"to_role": r["to"], "tx_signature": r.get("signature")} for r in (releases or [])],
           "private": not publish}
    if publish:
        out["published"] = publish
    if synthetic:
        out["synthetic"] = True
    problems = redaction_problems(out)
    if problems:
        raise ValueError("this lab record may not go public: " + "; ".join(problems[:3]))
    return out


def leaks(payload: dict, private: dict) -> list[str]:
    """Which private values (results, buyer, lab name, price...) appear anywhere in a public payload: [] when none."""
    import json
    text = json.dumps(payload, sort_keys=True)
    found = []

    def walk(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}")
        elif isinstance(v, (list, tuple)):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")
        elif isinstance(v, str) and len(v) >= 4 and v in text:
            found.append(path)
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 1000 and json.dumps(v) in text:
            found.append(path)
    walk(private, "private")
    return found


def record(payload: dict, *, root=None, claim: str | None = None) -> dict | None:
    """Append the public payload to Knos Record as a `verdict` line (None when Knos Record is not installed)."""
    try:
        from .. import record as rec
        return rec.append("verdict", payload, claim=claim, domain=payload.get("field", ""), root=root)
    except ImportError:
        return None
