"""When Qloo is not answering, the card says so. A failed Qloo call (HTTP 429, a 5xx, or no answer in time) marks the
report `qloo_down` with its code, and the card's first line says it; for the 8 sample chips the last real full card
is shown instead, marked `stale` with the time it was made. Each chip's card is its first real answer to a reader's
press (nothing is run at boot) and is kept with no expiry. Those last real cards live in this process's memory only:
never in the repository, the Pages build, a file, or any store copied to devnet."""
from __future__ import annotations

import copy
import re
import threading

# the front door's 8 sample chips (web/brand/hero.html): 7 ideas for the demand check and 1 paper for a crossing
CHIPS = ("an AI recipe planner for families", "a crypto podcast for beginners", "a quantum physics book for kids",
         "a solar powered music festival", "a probiotic kombucha brand", "a recycled ocean plastic swimwear brand",
         "a tiny home kit for first-time buyers", "10.1038/nature16521")
TIMEOUT_CODE = 504                       # no answer in time is said as a gateway timeout
_lock = threading.Lock()
_last: dict[str, dict] = {}


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


def keep(text: str, rep: dict) -> None:
    k = key(text)
    if k in CHIP_KEYS and real(rep):
        with _lock:
            _last[k] = copy.deepcopy(rep)


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
        return {**rec, "stage": rep.get("stage") or rec.get("stage"), "qloo_down": {"code": code},
                "stale": {"code": code, "from": rec.get("made")}}
    return {**rep, "qloo_down": {"code": code}}

