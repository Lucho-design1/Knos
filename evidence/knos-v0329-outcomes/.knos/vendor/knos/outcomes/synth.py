"""SYNTHETIC customer-support tickets for the outcome demo. Made up, every row says so (`synthetic` = 1).

An "AI agent" handles the treated tickets and people handle the control tickets, split by the spec's hash
(knos.outcomes.assign). A ticket counts as resolved without a human when it is solved, was not escalated and was not
reopened. The chances are parameters (`p_control`, `p_treated`), so the true lift of a generated set is chosen, not
found: this data shows how the measurement and the payment work, and says nothing about any real agent or help desk.
"""
from __future__ import annotations

import csv
import io
import random

from .assign import arm
from .spec import utc

FIELDS = ["ticket_id", "created_at", "channel", "handled_by", "status", "escalated", "reopened", "minutes", "synthetic"]


def tickets(spec: dict, n: int, *, seed: int, p_control: float = 0.45, p_treated: float = 0.53, before: int = 0) -> list[dict]:
    """`n` tickets inside the spec's window (and `before` more dated before it, the history), deterministic in `seed`."""
    rng = random.Random(seed)
    start, end = utc(spec["window"]["start"]), utc(spec["window"]["end"])
    salt, share = spec["control"]["salt"], float(spec["control"].get("share", 0.2))
    rows = []
    for i in range(n + before):
        tid = f"SYN-{seed % 1000:03d}-{i:06d}"
        t = rng.randrange(start - 30 * 86_400, start) if i >= n else rng.randrange(start, end)
        a = arm(tid, salt, share)
        p = p_treated if a == "treated" else p_control
        ok = rng.random() < p
        if ok:
            status, escalated, reopened = "solved", 0, 0
        else:
            kind = rng.random()
            status, escalated, reopened = (("solved", 0, 1) if kind < 0.3 else ("solved", 1, 0) if kind < 0.7 else ("open", 1, 0))
        rows.append({"ticket_id": tid, "created_at": _iso(t), "channel": rng.choice(("email", "chat", "web")),
                     "handled_by": "agent" if a == "treated" else "human", "status": status, "escalated": escalated, "reopened": reopened,
                     "minutes": rng.randint(2, 240), "synthetic": 1})
    rows.sort(key=lambda r: (r["created_at"], r["ticket_id"]))
    return rows


def _iso(t: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ---- known-bad variants, for the cheat checks ------------------------------------------------------------------------
def drop_treated_failures(rows: list[dict]) -> list[dict]:
    """A seller who deletes treated failures: removes every treated ticket that was not resolved (control drift)."""
    out = []
    for r in rows:
        bad = not (r["status"] == "solved" and r["escalated"] == 0 and r["reopened"] == 0)
        if r["handled_by"] == "agent" and bad:
            continue
        out.append(r)
    return out


def relabel(rows: list[dict], k: int = 50) -> list[dict]:
    """A seller who moves resolved control tickets to the agent: flips `handled_by` on the k latest resolved control rows."""
    out, done = [], 0
    for r in reversed(rows):
        r = dict(r)
        if done < k and r["handled_by"] == "human" and r["status"] == "solved" and r["escalated"] == 0 and r["reopened"] == 0:
            r["handled_by"] = "agent"
            done += 1
        out.append(r)
    return out[::-1]


def example_spec(*, start: str = "2026-09-01T00:00:00Z", end: str = "2026-09-29T00:00:00Z", salt: str = "5ca1ab1e" * 4,
                 funder: str = "9a6RmArU8cfKGqWRfXU2i8xGXsvVFiNs97ZMVuYyozcW", seller: str = "9ig9AXfoNrd5uPhdSFGujPoVsrxze5CGVFM6uusgQydG",
                 mint: str = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU", repository: str = "drexthealpha/knos-e2e", repository_id: int = 1401439243,
                 issue: int = 1, seq_start: int = 0, work_seconds: int = 30 * 86_400) -> dict:
    """The demo's spec with SYNTHETIC support tickets: three tiers (5%, 10%, 20% relative lift) under a cap of 30."""
    return {
        "version": 1,
        "title": "AI agent resolves support tickets without a human (SYNTHETIC data)",
        "synthetic": True,
        "parties": {"buyer": {"github": "drexthealpha", "id": 142920951}, "seller": {"github": "drexthealpha", "id": 142920951, "address": seller}},
        "metric": {"name": "resolved_without_human", "formula": "1 if status == 'solved' and escalated == 0 and reopened == 0 else 0",
                   "aggregate": "mean", "direction": "higher", "lift": "relative"},
        "data": {"source": "file", "path": "tickets.csv", "format": "csv", "id_field": "ticket_id", "time_field": "created_at",
                 "arm_field": "handled_by", "treated_value": "agent", "synthetic": True},
        "window": {"start": start, "end": end},
        "control": {"share": 0.2, "salt": salt},
        "success": {"min_lift": 0.05, "confidence": 0.95},
        "bootstrap": {"resamples": 1000, "seed": 20261013},
        "price": {"currency": "test-USDC", "unit_price": 1.0, "cap": 30.0},
        "tiers": [{"name": "lift-5", "min_lift": 0.05, "amount": 5.0}, {"name": "lift-10", "min_lift": 0.10, "amount": 10.0},
                  {"name": "lift-20", "min_lift": 0.20, "amount": 15.0}],
        "dispute_window_days": 7,
        "escrow": {"cluster": "devnet", "repository": repository, "repository_id": repository_id, "issue": issue, "funder": funder, "mint": mint,
                   "seq_start": seq_start, "work_seconds": work_seconds},
    }
