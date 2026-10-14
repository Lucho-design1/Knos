"""Per-claim accounts. A block gives each writable account a share of its compute (12,000,000 units per account per
block today, the cluster's `max_writable_account_units`), so transactions that all write one account queue behind
each other however many slots the block has. Knos keeps each claim (one token, one order, one payment) in accounts of
its own, and this module checks that.

    shared_writable({claim: [instructions...], ...}, ignore=(relayer,))   # accounts two claims both write

What is per claim today (programs-v2): the token account ["tok", payer, sha256(token)] (knos-oidc); the order
["ord", scope, source, seq], its money ["ov", order], its markers ["used", sha256(signature)], ["done", order, pr],
["q", order, kind], ["as", order, payee], ["hb", order] (knos-pay 2.1+). Shared by design: the fee account of a mint
(knos.settle.v2.fee_accounts spreads orders over several), the relayer (it pays), and for the 2.0 job instructions
only, the per-mint vault ["vault", mint] (docs/reference/PLATFORM.md: orders do not use it).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Hashable, Iterable

from solders.instruction import Instruction
from solders.pubkey import Pubkey

ACCOUNT_UNITS_PER_BLOCK = 12_000_000   # the writable-account limit a block applies (agave cost tracker, MAX_WRITABLE_ACCOUNT_UNITS)


def writable(ixs: Iterable[Instruction]) -> set[Pubkey]:
    return {m.pubkey for ix in ixs for m in ix.accounts if m.is_writable}


def shared_writable(by_claim: dict[Hashable, list[Instruction]], ignore: Iterable[Pubkey] = ()) -> dict[Pubkey, list]:
    """Every writable account that more than one claim's instructions write, with the claims that write it. Accounts
    in `ignore` (the relayer that pays, a fee account chosen per claim) are left out."""
    skip = set(ignore)
    seen: dict[Pubkey, list] = defaultdict(list)
    for claim, ixs in by_claim.items():
        for k in writable(ixs) - skip:
            seen[k].append(claim)
    return {k: v for k, v in seen.items() if len(v) > 1}


def per_block(units_per_claim: int) -> int:
    """How many claims that each write one shared account with `units_per_claim` compute units fit in a block: the
    ceiling per-claim accounts remove."""
    return ACCOUNT_UNITS_PER_BLOCK // max(1, units_per_claim)
