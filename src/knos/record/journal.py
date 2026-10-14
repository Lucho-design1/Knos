"""The Knos Record journal: one append-only JSON Lines file, every line hash-chained to the one before, and every line
also written to Sibyl's memory engine, in the tier the engine names it for:

    WARM       a research claim                    one entity (category `record_claim`) per claim, its latest state
    COLD       every experiment, verification,     one event in Sibyl's journal (append-only), for EVERY line,
               verdict, cheat caught, refusal,     claims and papers included: the second witness the verifier
               payout, refund, funding,            holds the file to
               graduation, split, anchor
    REFERENCE  a paper                             one reference document (`record:paper:<id>`)

A line is {"v", "seq", "ts", "kind", "tier", "claim", "domain", "payload", "prev", "hash"}: `prev` is the hash of the
line before ("0" * 64 for the first), `hash` is sha256 of the line's canonical JSON without `hash`. Editing, removing
or reordering any line breaks every hash after it. Removing lines from the END breaks no hash; Sibyl's journal still
holds them and the verifier says so (knos.record.verify), and an anchored Merkle root (knos.record.anchor) pins the
head on Solana devnet.

The record is public. A payload is refused before anything is written when it holds what looks like a secret, a key,
a token, an e-mail address or a local home path (`redaction_problems`). Amounts are the mint's smallest unit.
Synthetic demo data says so in its payload (`"synthetic": true`).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterator

VERSION = 1
GENESIS = "0" * 64
JOURNAL = "journal.jsonl"
TENANT = "knos-record"
CLAIM_CATEGORY = "record_claim"
PAPER_PREFIX = "record:paper:"
MAX_PAYLOAD_BYTES = 16 * 1024

COLD_KINDS = frozenset({"experiment", "verification", "verdict", "cheat", "refusal", "payout", "refund", "funding",
                        "graduation", "split", "anchor"})
KINDS = {**{k: "COLD" for k in COLD_KINDS}, "claim": "WARM", "paper": "REFERENCE"}
FIELDS = ("v", "seq", "ts", "kind", "tier", "claim", "domain", "payload", "prev", "hash")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@+-]{0,127}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class RecordError(ValueError):
    """Nothing was written: the line was refused, with one sentence saying why."""


# ---- where -----------------------------------------------------------------------------------------------------------

def default_root() -> Path:
    """$KNOS_RECORD_DIR, else <Knos home>/record (KNOS_HOME, else ~/.knos)."""
    given = os.environ.get("KNOS_RECORD_DIR")
    if given:
        return Path(given).expanduser()
    from .. import paths
    return paths.home() / "record"


def _root(root) -> Path:
    got = Path(root) if root is not None else default_root()
    if got.suffix == ".jsonl":
        got = got.parent
    return got


def journal_path(root=None) -> Path:
    return _root(root) / JOURNAL


def sibyl(root=None):
    """The record's memory: Sibyl's local store <root>/sibyl.db, tenant `knos-record`. ImportError when Sibyl's
    package is not installed: there is then no record to append to."""
    from ..proof import history
    return history.SibylStore.local(_root(root), TENANT)


# ---- hashing ---------------------------------------------------------------------------------------------------------

def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def line_hash(entry: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in entry.items() if k != "hash"})).hexdigest()


# ---- redaction -------------------------------------------------------------------------------------------------------

_SECRET_KEYS = re.compile(r"(secret|private_?key|privkey|passw|mnemonic|seed_?phrase|api_?key|keypair|cookie|authori[sz]ation|"
                          r"session|credential|(^|_)token$|^token|bearer|e-?mail)", re.I)
_SIG_KEYS = re.compile(r"(^|_)(tx|txs|sig|sigs|signature|signatures|transaction|transactions)$", re.I)
_HASH_KEYS = re.compile(r"(hash|digest|root|sha|head|prev|commit)", re.I)
_SECRET_TEXT = [
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "a GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "an API key"),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"), "a Slack token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS key"),
    (re.compile(r"-----BEGIN [A-Z ]*(PRIVATE KEY|CERTIFICATE)-----"), "a PEM key"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "a signed token (JWT)"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "an e-mail address"),
    (re.compile(r"(/home/[^/\s]+|/Users/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)"), "a local home path"),
]
_B58_64 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{86,90}$")      # 64 bytes in base58: a secret key, or a signature
_HEX_LONG = re.compile(r"^(0x)?[0-9a-fA-F]{128,}$")


def redaction_problems(payload: Any, where: str = "payload") -> list[str]:
    """Why `payload` may not go in a public record; empty when it may. A transaction signature is 64 bytes in base58,
    as a secret key is: it is taken only under a key that names it (tx, sig, signature, transaction)."""
    out: list[str] = []

    def walk(value: Any, path: str, key: str) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if not isinstance(k, str):
                    out.append(f"{path} has a key that is not text")
                    continue
                if _SECRET_KEYS.search(k):
                    out.append(f"{path}.{k} is named like a secret")
                walk(v, f"{path}.{k}", k)
            return
        if isinstance(value, (list, tuple)):
            if len(value) in (32, 64) and all(isinstance(x, int) and 0 <= x <= 255 for x in value):
                out.append(f"{path} is an array of {len(value)} bytes (a key's shape)")
                return
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]", key)
            return
        if isinstance(value, str):
            for rx, what in _SECRET_TEXT:
                if rx.search(value):
                    out.append(f"{path} holds {what}")
            if _B58_64.match(value) and not _SIG_KEYS.search(key):
                out.append(f"{path} is 64 bytes in base58 (a secret key's shape) under a key that does not name a signature")
            if _HEX_LONG.match(value) and not _HASH_KEYS.search(key):
                out.append(f"{path} is 64 bytes or more in hex under a key that does not name a hash")
            return
        if value is None or isinstance(value, (bool, int)):
            return
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                out.append(f"{path} is not a finite number")
            return
        out.append(f"{path} is a {type(value).__name__}, not JSON")

    walk(payload, where, "")
    return out


# ---- reading ---------------------------------------------------------------------------------------------------------

def read_lines(root=None) -> list[tuple[int, str]]:
    """(line number from 1, text) of every non-empty line of the journal; [] when there is none."""
    path = journal_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [(i, line) for i, line in enumerate(text.split("\n"), 1) if line.strip()]


def entries(root=None) -> list[dict]:
    """Every line of the journal as written, oldest first. RecordError on a line that is not a JSON object."""
    out = []
    for n, line in read_lines(root):
        try:
            got = json.loads(line)
        except ValueError:
            raise RecordError(f"line {n} of {journal_path(root)} is not JSON") from None
        if not isinstance(got, dict):
            raise RecordError(f"line {n} of {journal_path(root)} is not a JSON object")
        out.append(got)
    return out


def head(root=None) -> dict | None:
    got = entries(root)
    return got[-1] if got else None


# ---- writing ---------------------------------------------------------------------------------------------------------

@contextlib.contextmanager
def _locked(root: Path) -> Iterator[None]:
    """One writer at a time, across processes: an exclusive lock on <root>/journal.lock."""
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / "journal.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if sys.platform != "win32":
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            import msvcrt
            for _ in range(600):
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        yield
    finally:
        os.close(fd)                            # closing the descriptor releases either lock


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _check_id(what: str, value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _ID.match(value):
        raise RecordError(f"a {what} is 1-128 characters of letters, digits and ._:/#@+- ({value!r} is not)")
    problems = redaction_problems(value, what)
    if problems:
        raise RecordError(f"the {what} may not go in a public record: {problems[0]}")
    return value


def build(kind: str, payload: dict, prev: dict | None, *, claim: str | None = None, domain: str = "",
          ts: str | None = None) -> dict:
    """The next line after `prev` (None for the first), hashed; nothing is written. RecordError when it is refused."""
    if kind not in KINDS:
        raise RecordError(f"{kind!r} is not a record kind; the kinds are {', '.join(sorted(KINDS))}")
    if not isinstance(payload, dict):
        raise RecordError("a record's payload is a JSON object")
    problems = redaction_problems(payload)
    if problems:
        raise RecordError("the record is public and this payload may not go in it: " + "; ".join(problems[:3]))
    try:
        size = len(canonical(payload))
    except (TypeError, ValueError) as why:
        raise RecordError(f"the payload is not JSON: {why}") from None
    if size > MAX_PAYLOAD_BYTES:
        raise RecordError(f"the payload is {size} bytes; a record line holds at most {MAX_PAYLOAD_BYTES} (put a hash of the rest in it)")
    claim = _check_id("claim id", claim)
    if kind in ("claim", "paper") and not claim:
        raise RecordError(f"a {kind} line names its {'claim' if kind == 'claim' else 'paper'} id")
    domain = _check_id("domain", domain) or ""
    entry = {"v": VERSION, "seq": (prev["seq"] + 1) if prev else 0, "ts": ts or _now(), "kind": kind, "tier": KINDS[kind],
             "claim": claim, "domain": domain, "payload": payload, "prev": prev["hash"] if prev else GENESIS}
    entry["hash"] = line_hash(entry)
    return entry


def _remember(store, entry: dict) -> None:
    """The line in Sibyl, in its tier; every line is also one COLD journal event (the verifier's second witness)."""
    if entry["tier"] == "WARM":
        store.put(CLAIM_CATEGORY, entry["claim"], {**entry["payload"], "_seq": entry["seq"], "_hash": entry["hash"],
                                                   "_domain": entry["domain"]})
    elif entry["tier"] == "REFERENCE":
        store.set_reference(PAPER_PREFIX + entry["claim"], {**entry["payload"], "_seq": entry["seq"], "_hash": entry["hash"]},
                            kind="knos-record-paper")
    store.journal(evaluated={"kind": entry["kind"], "claim": entry["claim"], "domain": entry["domain"]},
                  acted={"seq": entry["seq"], "hash": entry["hash"]}, extra={"record": entry})


def append(kind: str, payload: dict, *, claim: str | None = None, domain: str = "", root=None, store=None,
           ts: str | None = None) -> dict:
    """Append one line to the record and return it. Written to Sibyl first, then to the file; refused (RecordError)
    before anything is written when the line may not go in a public record. `store` defaults to Sibyl's local store
    beside the file (ImportError without Sibyl: no memory, no record)."""
    where = _root(root)
    with _locked(where):
        entry = build(kind, payload, head(where), claim=claim, domain=domain, ts=ts)
        st = store if store is not None else sibyl(where)
        _remember(st, entry)
        with open(journal_path(where), "a", encoding="utf-8", newline="\n") as f:
            f.write(canonical(entry).decode("utf-8") + "\n")
            f.flush()
            with contextlib.suppress(OSError):
                os.fsync(f.fileno())
    return entry


def claim(claim_id: str, payload: dict, *, domain: str = "", root=None, store=None, ts: str | None = None) -> dict:
    """A research claim (WARM): its state now. Writing it again records the new state; the old one stays in the file."""
    return append("claim", payload, claim=claim_id, domain=domain, root=root, store=store, ts=ts)


def paper(ref_id: str, payload: dict, *, domain: str = "", root=None, store=None, ts: str | None = None) -> dict:
    """A paper (REFERENCE): title, link, content hash. Never the paper's text."""
    return append("paper", payload, claim=ref_id, domain=domain, root=root, store=store, ts=ts)


# ---- what Sibyl holds ------------------------------------------------------------------------------------------------

def remembered(store) -> list[dict]:
    """Every record line Sibyl's journal holds for this tenant, oldest first by seq."""
    out = []
    for ev in store.events(limit=10_000_000):
        extra = ev.get("extra")
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except ValueError:
                continue
        got = extra.get("record") if isinstance(extra, dict) else None
        if isinstance(got, dict) and "seq" in got and "hash" in got:
            out.append(got)
    return sorted(out, key=lambda e: (int(e.get("seq", -1)), str(e.get("hash"))))


def claim_state(claim_id: str, root=None, store=None) -> dict:
    """The claim as Sibyl holds it now (WARM), {} when Sibyl holds none."""
    st = store if store is not None else sibyl(root)
    return st.get(CLAIM_CATEGORY, claim_id)


def claim_events(claim_id: str, root=None, store=None) -> list[dict]:
    """Every line about one claim, from Sibyl's journal (COLD), oldest first."""
    st = store if store is not None else sibyl(root)
    return [e for e in remembered(st) if e.get("claim") == claim_id]


def is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))
