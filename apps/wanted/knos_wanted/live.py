"""What the app keeps for a person across devices and shows live, with no account beyond the passkey:

  draft_save / draft_get   the brief a person is writing, kept per signed-in user (the passkey is the key): open the app
                           on another device, sign in with the same passkey, the draft is there (cross-device continuity);
                           every save is a version (the undo timeline), 50 kept
  presence(...)            who else is on a project page now: a pointer position and a name, kept 15 seconds; the page
                           draws them as live cursors (co-browsing a project with whoever has its link)
  stream(h, job, since)    a crossing's steps as Server-Sent Events while it runs (the app reads them as they come)
"""
from __future__ import annotations

import json
import threading
import time

from . import escrow

KEEP_S = 15
MAX_VERSIONS = 50
_lock = threading.Lock()
_presence: dict[str, dict[str, dict]] = {}


def _dir():
    d = escrow._state_dir() / "valley" / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _who(user: dict) -> str:
    import hashlib
    return hashlib.sha256(str(user.get("sub") or "").encode()).hexdigest()[:32]


def draft_save(user: dict, brief: dict, title: str = "") -> dict:
    if not user or not user.get("sub"):
        raise ValueError("sign in with your passkey first: the draft is kept for your passkey")
    if not isinstance(brief, dict) or len(json.dumps(brief)) > 20_000:
        raise ValueError("brief: a JSON brief under 20 kB")
    f = _dir() / f"{_who(user)}.json"
    with _lock:
        got = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"versions": []}
        got["versions"] = (got["versions"] + [{"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "title": str(title)[:120], "brief": brief}])[-MAX_VERSIONS:]
        f.write_text(json.dumps(got), encoding="utf-8")
    return {"versions": len(got["versions"]), "saved": got["versions"][-1]["at"]}


def draft_get(user: dict) -> dict:
    if not user or not user.get("sub"):
        raise ValueError("sign in with your passkey first")
    f = _dir() / f"{_who(user)}.json"
    got = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"versions": []}
    return {"latest": got["versions"][-1] if got["versions"] else None, "timeline": [{"at": v["at"], "title": v["title"]} for v in got["versions"]]}


def draft_forget(user: dict) -> dict:
    f = _dir() / f"{_who(user)}.json"
    if f.exists():
        f.unlink()
    return {"forgotten": True}


def presence(page: str, me: str, x: float, y: float, label: str) -> dict:
    """Write this viewer's pointer on `page` and read everyone else's seen in the last KEEP_S seconds."""
    page, me = str(page)[:80], str(me)[:40]
    now = time.time()
    with _lock:
        room = _presence.setdefault(page, {})
        room[me] = {"x": max(0.0, min(1.0, float(x))), "y": max(0.0, min(1.0, float(y))), "label": str(label)[:40], "at": now}
        for k in [k for k, v in room.items() if now - v["at"] > KEEP_S]:
            room.pop(k)
        others = [{"id": k, **{f: v[f] for f in ("x", "y", "label")}} for k, v in room.items() if k != me]
    return {"page": page, "others": others, "here": len(others) + 1}


def stream(h, job: str, since: int = 0, within: float = 120.0) -> None:
    """Server-Sent Events of a crossing: one event per new step, then `done` (or a timeout comment)."""
    from . import agent
    h.send_response(200)
    for k, v in (("Content-Type", "text/event-stream"), ("Cache-Control", "no-cache"), ("X-Accel-Buffering", "no")):
        h.send_header(k, v)
    h.end_headers()
    end = time.time() + within
    while time.time() < end:
        got = agent.poll(job, since)
        if got is None:
            h.wfile.write(b"event: error\ndata: {\"error\": \"unknown crossing\"}\n\n")
            h.wfile.flush()
            return
        for s in got.get("steps") or []:
            h.wfile.write(f"data: {json.dumps(s, default=str)}\n\n".encode())
        since = got.get("total", since)
        h.wfile.flush()
        if got.get("status") in ("done", "error"):
            h.wfile.write(f"event: done\ndata: {json.dumps({'status': got.get('status')})}\n\n".encode())
            h.wfile.flush()
            return
        time.sleep(0.5)
    h.wfile.write(b": still running; ask again\n\n")
    h.wfile.flush()
