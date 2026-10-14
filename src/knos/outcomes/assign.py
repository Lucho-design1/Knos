"""Who is in the control group: decided by a hash, so either side can recompute it and neither can choose it.

    position(item) = the first 8 bytes of sha256("knos-outcome:v1:" + salt + ":" + item id), big-endian, / 2**64
    arm(item)      = "control" when position < share, else "treated"

The salt is public and written in the spec, which both parties sign and the orders' terms hash before the window
opens; the item ids are the data's own. So the split is fixed before any item exists, the same on every machine,
and a party who wants an item on the other side would have to change its id, which the data's own record shows.
Nothing random is drawn at run time.
"""
from __future__ import annotations

import hashlib
import math

PREFIX = b"knos-outcome:v1:"


def position(item_id: str, salt: str) -> float:
    """Where an item falls in [0, 1)."""
    digest = hashlib.sha256(PREFIX + salt.encode() + b":" + str(item_id).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def arm(item_id: str, salt: str, share: float) -> str:
    return "control" if position(item_id, salt) < share else "treated"


def split(ids, salt: str, share: float) -> dict[str, str]:
    return {str(i): arm(str(i), salt, share) for i in ids}


def tolerance(share: float, n: int, given: float | None = None) -> float:
    """How far the observed control share may be from `share` before the split counts as drifted: the spec's own
    `control.tolerance` when it has one, else four standard errors of a share over n items (no floor). With an honest
    hash split the observed share is a binomial draw, so four standard errors are crossed about once in 16,000 runs.

    The limit, said plainly: this catches deletions or additions large enough to move the share by four standard
    errors. With 10,000 items and a share of 0.2 that is about 0.016: deleting 900 of the treated group's failures is
    caught, deleting 200 is not. Small deletions are stopped by who holds the data (the buyer's own record, which the
    seller cannot edit), not by this check."""
    if given is not None:
        return float(given)
    if n <= 0:
        return 1.0
    return 4 * math.sqrt(share * (1 - share) / n)
