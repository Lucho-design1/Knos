"""Makeable: can the result be made at a profit? A cost check from supplied quotes against the locked price.

Every quote must name its source (a supplier's quote, a price page with its date): an unsourced number refuses. A
quote past its `valid_until` refuses. Cost = sum(unit_cost * quantity) + fees (MONEY's fee config, passed in), and
the check passes when cost <= locked_price * (1 - min_margin). All amounts are in one currency and one unit.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass

from .check import Check

KINDS = ("compute", "cloud_lab", "manufacturing", "materials", "labour", "logistics", "other")


@dataclass(frozen=True)
class Quote:
    kind: str
    supplier: str
    unit_cost: float
    quantity: float = 1
    currency: str = "USD"
    source: str = ""                # where the number comes from: required
    valid_until: str = ""           # ISO date; empty = no expiry stated

    def total(self) -> float:
        return float(self.unit_cost) * float(self.quantity)


def _today() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


def makeable(quotes, *, locked_price: float, min_margin: float = 0.0, fees: float = 0.0, required_kinds=(),
             today: _dt.date | None = None) -> Check:
    qs = [q if isinstance(q, Quote) else Quote(**q) for q in quotes]
    today = today or _today()
    reasons = []
    if locked_price <= 0:
        reasons.append("no price is locked")
    if not 0 <= min_margin < 1:
        raise ValueError("min_margin is a share between 0 and 1")
    if not qs:
        reasons.append("no quotes")
    for q in qs:
        if q.kind not in KINDS:
            reasons.append(f"quote from {q.supplier}: kind {q.kind!r} is not one of {', '.join(KINDS)}")
        if not str(q.source).strip():
            reasons.append(f"quote from {q.supplier} ({q.kind}) has no source")
        if q.unit_cost < 0 or q.quantity <= 0:
            reasons.append(f"quote from {q.supplier} ({q.kind}): a cost or quantity that cannot be")
        if q.valid_until:
            try:
                if _dt.date.fromisoformat(q.valid_until[:10]) < today:
                    reasons.append(f"quote from {q.supplier} ({q.kind}) expired on {q.valid_until[:10]}")
            except ValueError:
                reasons.append(f"quote from {q.supplier} ({q.kind}): valid_until {q.valid_until!r} is not a date")
    currencies = sorted({q.currency for q in qs})
    if len(currencies) > 1:
        reasons.append(f"quotes in more than one currency ({', '.join(currencies)}); convert them first, with the rate's source")
    missing = [k for k in required_kinds if k not in {q.kind for q in qs}]
    if missing:
        reasons.append("no quote for " + ", ".join(missing))
    cost = sum(q.total() for q in qs) + float(fees)
    ceiling = float(locked_price) * (1 - float(min_margin))
    if not reasons and cost > ceiling:
        reasons.append(f"cost {cost:.2f} is above {ceiling:.2f} (locked price {float(locked_price):.2f} less a "
                       f"{min_margin:.0%} margin)")
    by_kind: dict = {}
    for q in qs:
        by_kind[q.kind] = by_kind.get(q.kind, 0.0) + q.total()
    ev = {"cost": round(cost, 6), "fees": float(fees), "locked_price": float(locked_price), "ceiling": round(ceiling, 6),
          "margin": round(1 - cost / float(locked_price), 6) if locked_price > 0 else None, "by_kind": by_kind,
          "currency": currencies[0] if len(currencies) == 1 else None, "quotes": [asdict(q) for q in qs]}
    return Check("makeable", not reasons, reasons, ev)
