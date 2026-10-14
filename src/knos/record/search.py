"""Search the record through Sibyl's cross-tier search, which always says WHY it returned what it did
(sibyl-memory-client 0.8.1: MemoryClient.search -> verdicts.SearchResults with .verdict; verdicts.refine_zero tells
"nothing matched" from "nothing was ever written"). A buyer asks "was this spec verified before, was this cheat seen
before?" and gets rows and a sentence it can act on, never a silent empty list.

    search(query, root=None, store=None, tiers=None, limit=20) -> {"rows", "verdict", "said", "store"}

`store` is the free-tier status Sibyl reports for the local file (size and soft cap), so an operator sees when the
record outgrows the free tier before a write is refused."""
from __future__ import annotations

from . import journal


def search(query: str, root=None, store=None, tiers: tuple[str, ...] | None = None, limit: int = 20) -> dict:
    from sibyl_memory_client import verdicts
    s = store if store is not None else journal.sibyl(root)
    client = getattr(s, "client", s)
    hits = client.search(query, limit=max(1, min(int(limit), 100)), tiers=tiers)
    if not hits:
        hits = verdicts.refine_zero(client, hits)
    v = getattr(hits, "verdict", None)
    rows = [dict(h) for h in hits]
    out = {"query": query, "rows": rows, "verdict": v.as_dict() if v is not None else None,
           "said": v.explain() if v is not None else f"{len(rows)} row(s) matched."}
    try:
        out["store"] = client.free_tier_status()
    except Exception:  # noqa: BLE001 - a status the engine cannot give is left out, never guessed
        out["store"] = None
    return out
