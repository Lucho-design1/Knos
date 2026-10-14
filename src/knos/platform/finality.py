"""How deep a transaction must be before Knos counts it: one setting, so a faster finality (Alpenglow's target is
about 150 ms, SIMD-0326) needs no code change, only a different answer from the cluster.

    KNOS_COMMITMENT   processed | confirmed (default) | finalized

`processed`: the node that answered has executed it (it can still be dropped by a fork). `confirmed`: a
supermajority voted on its block. `finalized`: its block is rooted. These are the cluster's own words
(https://solana.com/docs/rpc#configuring-state-commitment); Knos only chooses which one it waits for.
"""
from __future__ import annotations

import os

COMMITMENTS = ("processed", "confirmed", "finalized")
DEFAULT = "confirmed"
ENV = "KNOS_COMMITMENT"


def commitment(value: str | None = None) -> str:
    """The commitment to wait for: `value`, else KNOS_COMMITMENT, else confirmed. ValueError for any other word."""
    word = (value if value is not None else os.environ.get(ENV, "") or DEFAULT).strip().lower()
    if word not in COMMITMENTS:
        raise ValueError(f"{ENV} must be one of {', '.join(COMMITMENTS)}; got {word!r}")
    return word


def good(value: str | None = None) -> tuple[str, ...]:
    """The confirmation statuses that satisfy a commitment: a deeper status always satisfies a shallower one."""
    c = commitment(value)
    return COMMITMENTS[COMMITMENTS.index(c):]


def reached(status: dict | None, value: str | None = None) -> bool:
    """Whether one entry of getSignatureStatuses has reached the commitment."""
    return bool(status) and status.get("confirmationStatus") in good(value)  # type: ignore[union-attr]
