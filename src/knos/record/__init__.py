"""Knos Record: what Knos verified, refused, caught and paid, as one public, append-only, hash-chained JSON Lines file,
held in Sibyl's memory engine tier by tier and anchored on Solana devnet by Merkle root (docs/RECORD.md).

    from knos import record
    record.claim("claim-42", {"title": "...", "spec_hash": "..."}, domain="ml")         WARM  (a research claim)
    record.append("verdict", {"spec_hash": "...", "passed": False, "cheat": "test_edited"}, claim="claim-42")   COLD
    record.paper("arxiv:2401.00001", {"title": "...", "sha256": "..."})                 REFERENCE
    record.anchor(keypair="wallet.json")      the Merkle root of every unanchored line, in one devnet Memo transaction
    record.verify()                           recompute every hash and root; check them on chain and against Sibyl

Other parts of Knos write records only through `append`, `claim` and `paper`; nothing else writes the file.
"""

from __future__ import annotations

from .anchoring import AnchorError, anchor, chain_memo, plan
from .journal import (COLD_KINDS, KINDS, RecordError, append, claim, claim_events, claim_state, default_root, entries,
                      head, journal_path, line_hash, paper, redaction_problems, remembered, sibyl)
from .merkle import check_proof, proof, root as merkle_root
from .verifier import verify

__all__ = ["AnchorError", "COLD_KINDS", "KINDS", "RecordError", "anchor", "append", "chain_memo", "check_proof", "claim",
           "claim_events", "claim_state", "default_root", "entries", "head", "journal_path", "line_hash", "merkle_root",
           "paper", "plan", "proof", "redaction_problems", "remembered", "sibyl", "verify"]
