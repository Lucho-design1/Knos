"""Products that are not built yet: a maker's demand report opened for pre-orders.

A product is not a Qloo entity (it does not exist yet). What Qloo can rank is the EXISTING product the maker
confirmed as its proxy in the demand report, so each listing keeps that proxy's id and type. Kept in the server's
private state folder (KNOS_WANTED_STATE, default .cache/state, git-ignored), never in the repository.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()
MAX = 500


def _path() -> Path:
    d = Path(os.environ.get("KNOS_WANTED_STATE") or ".cache/state")
    d.mkdir(parents=True, exist_ok=True)
    return d / "products.json"


def products() -> list[dict]:
    try:
        got = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return got if isinstance(got, list) else []


def publish(rep: dict, title: str) -> dict:
    title = " ".join(str(title or "").split())[:80]
    if len(title) < 3:
        raise ValueError("name the product (3 to 80 characters)")
    main = (rep.get("chosen") or {}).get("proxies") or []
    if not main:
        raise ValueError("the report has no confirmed proxy")
    item = {"report_hash": rep["hash"], "title": title, "type": rep["type"], "proxy": main[0], "lean": rep["lean"]["word"],
            "mode": rep["mode"], "synthetic": rep["mode"] != "live", "listed": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    with _lock:
        items = [p for p in products() if p.get("report_hash") != rep["hash"]] + [item]
        p = _path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(items[-MAX:]), encoding="utf-8")
        os.replace(tmp, p)
    return item


def get(report_hash: str) -> dict | None:
    return next((p for p in products() if p.get("report_hash") == report_hash), None)
