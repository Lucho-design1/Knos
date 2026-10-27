"""When Qloo is not answering, the card says so. A failed Qloo call (HTTP 429, a 5xx, or no answer in time) marks the
report `qloo_down` with its code, and the card's first line says it; for the 8 sample chips the last real full card
is shown instead, marked `stale` with the time it was made. Each chip's card is its first real answer to a reader's
press (nothing is run at boot) and is kept with no expiry. They survive a redeploy in one private place: a Render secret
file (KNOS_RECORDED_FILE, by default /etc/secrets/knos-recorded.json), read at boot. Never the repository, the Pages
build, Sibyl, devnet or any public store. A new real card is written back to that file at most once in 10 minutes, and
only when this server was given the means to (KNOS_RECORDED_UPLOAD_KEY and RENDER_SERVICE_ID); without them it stays in
memory until the operator uploads the file from their own machine."""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import urllib.request

# the front door's 8 sample chips (web/brand/hero.html): 7 ideas for the demand check and 1 paper for a crossing
CHIPS = ("an AI recipe planner for families", "a crypto podcast for beginners", "a quantum physics book for kids",
         "a solar powered music festival", "a probiotic kombucha brand", "a recycled ocean plastic swimwear brand",
         "a tiny home kit for first-time buyers", "10.1038/nature16521")
TIMEOUT_CODE = 504                       # no answer in time is said as a gateway timeout
DEFAULT_FILE = "/etc/secrets/knos-recorded.json"
WRITE_EVERY_S = 600
_lock = threading.Lock()
_last: dict[str, dict] = {}
_write = {"at": 0.0, "timer": None}


def key(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


CHIP_KEYS = {key(c) for c in CHIPS}


def failure(rep: dict) -> int | None:
    """The HTTP code of the first Qloo call that failed for want of an answer (429, a 5xx, a timeout), or None."""
    for c in rep.get("calls") or []:
        err = str(c.get("error") or "")
        if not err:
            continue
        m = re.search(r"HTTP (\d{3})", err)
        if m and (m[1] == "429" or m[1].startswith("5")):
            return int(m[1])
        if "did not answer" in err or "had not answered" in err:
            return TIMEOUT_CODE
    return None


def real(rep: dict) -> bool:
    """A full card made of real Qloo answers: live, no failed call, the whole check (not the verdict card alone)."""
    return (str(rep.get("label") or "").startswith("LIVE") and rep.get("stage") != "verdict" and failure(rep) is None
            and not rep.get("qloo_down") and not rep.get("stale"))


def path() -> str:
    return os.environ.get("KNOS_RECORDED_FILE") or DEFAULT_FILE


def load(file: str | None = None) -> int:
    """The recorded cards of the private file into memory (at boot); how many chips have one."""
    try:
        doc = json.loads(open(file or path(), encoding="utf-8").read())
    except (OSError, ValueError):
        return 0
    from . import check                   # a card recorded before a segment's name was known to be sensitive is shown without it
    from . import metros                  # and its launch terms written in, by the rule every page draws (metros.launch_terms)
    from . import signals                 # and what each Qloo signal changes on it (the published table)
    cards = {k: metros.with_terms(check.retie(check.scrub(v))) for k, v in (doc.get("cards") or {}).items() if k in CHIP_KEYS and isinstance(v, dict) and real(v)}
    cards = {k: {**v, "signals": signals.for_card(v)} for k, v in cards.items()}
    with _lock:
        for k, v in cards.items():
            if k not in _last or (v.get("made") or "") > (_last[k].get("made") or ""):
                _last[k] = v
        return len(_last)


def _upload() -> None:
    """Write the recorded cards back to the Render secret file (only with KNOS_RECORDED_UPLOAD_KEY and RENDER_SERVICE_ID)."""
    k, sid = os.environ.get("KNOS_RECORDED_UPLOAD_KEY"), os.environ.get("RENDER_SERVICE_ID")
    with _lock:
        _write.update(at=time.time(), timer=None)
        doc = {"v": 1, "about": "the sample chips' last real full cards (private: a Render secret file, never public)", "cards": dict(_last)}
    if not (k and sid):
        return
    body = json.dumps({"content": json.dumps(doc, separators=(",", ":"), ensure_ascii=False)}).encode()
    req = urllib.request.Request(f"https://api.render.com/v1/services/{sid}/secret-files/{os.path.basename(path())}", method="PUT", data=body,
                                 headers={"Authorization": "Bearer " + k, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as why:  # noqa: BLE001 - a write that fails keeps the card in memory, said in the log
        print(f"knos recorded: write-back failed ({type(why).__name__})", flush=True)


def _write_soon() -> None:
    """At most one write-back in WRITE_EVERY_S, after a new real card."""
    with _lock:
        if _write["timer"] is not None:
            return
        wait = max(0.0, _write["at"] + WRITE_EVERY_S - time.time())
        _write["timer"] = threading.Timer(wait, _upload)
        _write["timer"].daemon = True
        _write["timer"].start()


def keep(text: str, rep: dict) -> None:
    k = key(text)
    if k in CHIP_KEYS and real(rep):
        with _lock:
            _last[k] = copy.deepcopy(rep)
        if os.environ.get("KNOS_RECORDED_UPLOAD_KEY"):
            _write_soon()


def by_hash(h: str) -> dict | None:
    """A recorded sample card by its report hash (a copy), or None."""
    with _lock:
        r = next((v for v in _last.values() if v.get("hash") == h), None)
    return copy.deepcopy(r) if r else None


def recording(text: str) -> dict | None:
    with _lock:
        r = _last.get(key(text))
    return copy.deepcopy(r) if r else None


def honest(text: str, rep: dict) -> dict:
    """The report as the card should show it: kept when real; when Qloo failed, the chip's last real card marked stale,
    or the report itself marked qloo_down."""
    code = failure(rep)
    if code is None:
        keep(text, rep)
        return rep
    rec = recording(text)
    if rec:
        from . import qloo_rest                     # /status/qloo counts the answers served from recordings today
        qloo_rest._today()["recorded"] = qloo_rest._today().get("recorded", 0) + 1
        return {**rec, "stage": rep.get("stage") or rec.get("stage"), "qloo_down": {"code": code},
                "stale": {"code": code, "from": rec.get("made")}}
    return {**rep, "qloo_down": {"code": code}}

