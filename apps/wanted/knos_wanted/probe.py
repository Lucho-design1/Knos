"""Which Qloo endpoints does this key serve?  python -m knos_wanted probe

Calls each endpoint the app uses once, with documented parameters, and records ONLY the HTTP status code of each
call (never any response data) in .cache/probe.json (git-ignored). The app then skips what the key does not serve
and labels that report section "not served". Ids needed to chain calls (an entity id from /search, a tag id from
/v2/tags) are held in memory for the run only and are not written anywhere.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .qloo import ENDPOINTS, Qloo

TYPES = ["urn:entity:brand", "urn:entity:place", "urn:entity:artist", "urn:entity:destination", "urn:entity:movie",
         "urn:entity:podcast", "urn:entity:book", "urn:entity:tv_show", "urn:entity:video_game", "urn:entity:videogame"]


def _status(q: Qloo, endpoint: str, params: dict) -> tuple[int | None, dict | None]:
    status, body = q.raw(q.url(endpoint, params))
    data = None
    if status == 200:
        try:
            data = json.loads(body)
        except ValueError:
            data = None
    return status, data


def run(q: Qloo | None = None, out: Path | None = None) -> dict:
    q = q or Qloo(unserved=set())
    if not q.live:
        raise SystemExit("QLOO_API_KEY is not set: nothing to probe (the app runs on MOCK data until it is).")
    res: dict[str, dict] = {}
    st, data = _status(q, "search", {"query": "coffee", "types": "urn:entity:brand", "take": 2})
    res["search"] = {"status": st}
    ids = [e.get("entity_id") for e in (data or {}).get("results", []) if isinstance(e, dict) and e.get("entity_id")]
    st, data = _status(q, "tags", {"filter.query": "coffee", "take": 1})
    res["tags"] = {"status": st}
    tags = [t.get("tag_id") or t.get("id") for t in ((data or {}).get("results") or {}).get("tags", []) if isinstance(t, dict)]
    tag = next((t for t in tags if t), None)
    sig = {"signal.interests.tags": tag} if tag else {"signal.interests.entities": ",".join(ids[:1])}
    res["insights"] = {"status": _status(q, "insights", {"filter.type": "urn:entity:brand", **sig, "take": 1})[0]}
    res["demographics"] = {"status": _status(q, "demographics", sig)[0]}
    res["heatmap"] = {"status": _status(q, "heatmap", {"filter.location.query": "New York", **sig})[0]}
    end = datetime.now(timezone.utc).date()
    res["trending"] = {"status": _status(q, "trending", {"filter.type": "urn:entity:brand", "signal.interests.entities": ",".join(ids[:1]),
                                                         "filter.start_date": (end - timedelta(days=28)).isoformat(),
                                                         "filter.end_date": end.isoformat()})[0] if ids else None}
    res["compare"] = {"status": _status(q, "compare", {"a.signal.interests.entities": ids[0], "b.signal.interests.entities": ids[1],
                                                       "take": 1})[0] if len(ids) >= 2 else None}
    types = {t: _status(q, "insights", {"filter.type": t, **sig, "take": 1})[0] for t in TYPES} if (tag or ids) else {}
    got = {"read": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "base_url": q.base_url,
           "note": "HTTP status codes only; no Qloo response data is stored here",
           "endpoints": {k: res.get(k, {"status": None}) for k in ENDPOINTS}, "insights_filter_types": types}
    out = out or Path(os.environ.get("KNOS_WANTED_CACHE") or ".cache/qloo").parent / "probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8")
    return got


def main() -> int:
    got = run()
    for k, v in got["endpoints"].items():
        print(f"{k:13} {v['status']}")
    for k, v in got["insights_filter_types"].items():
        print(f"  insights {k:24} {v}")
    return 0
