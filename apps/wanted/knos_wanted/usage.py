"""The public usage counter: demand checks run and Ready briefs made, persisted in the app's store (valley, mirrored on
devnet so a redeploy keeps it), and the transactions of the knos_pay program on devnet, counted with
getSignaturesForAddress. GET /api/usage answers all three; the front door shows them."""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from pathlib import Path

KEY = "usage-counter"
_lock = threading.Lock()
_chain: dict = {"at": 0.0, "n": None}
CHAIN_S = 15                          # how long a devnet count is reused (a count takes about 8 s)


def _doc() -> dict:
    from . import valley
    return valley._safe_load("pages", KEY) or {"checks": 0, "briefs": 0,
                                               "since": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")}


def bump(checks: int = 0, briefs: int = 0) -> None:
    """Count what was just made; a failure to count never fails the request."""
    from . import valley
    try:
        with _lock:
            d = _doc()
            d["checks"] = int(d.get("checks") or 0) + checks
            d["briefs"] = int(d.get("briefs") or 0) + briefs
            valley._save("pages", KEY, d)
    except Exception as why:  # noqa: BLE001
        print(f"knos usage: not counted: {type(why).__name__}: {str(why)[:120]}", flush=True)


def program() -> str:
    from knos.settle import v2
    return json.loads((Path(v2.__file__).parent / "program_ids.json").read_text(encoding="utf-8"))["knos_pay"]


def chain_count(url: str | None = None) -> int:
    """Every signature of the knos_pay program on devnet (getSignaturesForAddress, 1,000 a page, oldest last)."""
    from knos import chain

    from . import escrow
    url = url or escrow.ledger().url
    n, before = 0, None
    while True:
        opts: dict = {"limit": 1000, "commitment": "confirmed", **({"before": before} if before else {})}
        page = chain.call(url, "getSignaturesForAddress", [program(), opts]) or []
        n += len(page)
        if len(page) < 1000:
            return n
        before = page[-1]["signature"]


def counts() -> dict:
    d = _doc()
    if time.time() - _chain["at"] > CHAIN_S or _chain["n"] is None:
        try:
            _chain.update(n=chain_count(), at=time.time())
        except Exception:  # noqa: BLE001
            pass
    return {"checks": int(d.get("checks") or 0), "briefs": int(d.get("briefs") or 0), "since": d.get("since"),
            "payouts": _chain["n"], "program": program(), "cluster": "devnet",
            "payouts_counted": dt.datetime.fromtimestamp(_chain["at"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if _chain["at"] else None}
