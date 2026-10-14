"""Writing the loop's history to Knos Record.

With knos.record installed (RECORD's API) every line goes through it, nothing else writes its journal:
    record.claim(claim_id, payload, domain=, root=)       the research claim (Sibyl WARM entity, latest state)
    record.paper(ref_id, payload, root=)                  program.md + idea.md, by hash (Sibyl REFERENCE)
    record.append(kind, payload, claim=, domain=, root=)  each experiment / verdict / cheat / refusal / graduation /
                                                          split (Sibyl COLD journal event + one hash-chained line)
    record.verify(root)                                   check the chain
    record.anchor(root, keypair=, send=)                  anchor its Merkle root on devnet (opt-in: --anchor)

Without it (an older install) the same entry shape is kept by LocalRecord: a hash-chained JSONL of its own
(<root>/autoresearch-journal.jsonl) plus the same three Sibyl tiers in <root>/sibyl.db (knos.proof.history's
SibylStore), so Sibyl stays the memory either way. Its Merkle root is computed exactly as knos.record.merkle does
(RFC 9162: leaf sha256(0x00||hash), node sha256(0x01||l||r), split at the largest power of two below n).

Payloads are public and redacted: hashes, scores, decisions, cheat categories, amounts in micro-units; never source
code, keys or personal data. Text that came from an agent or a candidate (a change's one-line description, a crash's
last line) is kept only when it is short plain words; anything else is replaced by its sha256 (`sanitize`), so a
candidate cannot make the record refuse a line and stop the run.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

DOMAIN = "ml-research"
TIERS = {"claim": "WARM", "paper": "REFERENCE"}
GENESIS = "0" * 64
PLAIN = re.compile(r"^[A-Za-z0-9 _:'.,;>()+=*<\-]{0,160}$")       # no '/', '@', '\\': no paths, addresses, URLs
HASHY_KEYS = re.compile(r"(hash|digest|root|sha|head|prev|commit)", re.I)


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sanitize(value, key: str = ""):
    """Every free-text string that is not short plain words becomes 'sha256:<hex>' (hash-named keys are kept)."""
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, key) for v in value]
    if isinstance(value, str) and not HASHY_KEYS.search(key) and not PLAIN.match(value):
        return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
    return value


def _leaf(h: str) -> bytes:
    return hashlib.sha256(b"\x00" + bytes.fromhex(h)).digest()


def _root(leaves: list[bytes]) -> bytes:
    if len(leaves) == 1:
        return leaves[0]
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return hashlib.sha256(b"\x01" + _root(leaves[:k]) + _root(leaves[k:])).digest()


def merkle_root(hashes: list[str]) -> str:
    """The batch's root as knos.record.merkle.root computes it; sha256 of nothing for an empty batch."""
    if not hashes:
        return hashlib.sha256(b"").hexdigest()
    return _root([_leaf(h) for h in hashes]).hex()


class LocalRecord:
    backend = "knos.autoresearch.recorder.LocalRecord (knos.record not installed)"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "autoresearch-journal.jsonl"
        self._store = None

    @property
    def store(self):
        if self._store is None:
            from knos.proof.history import SibylStore
            self._store = SibylStore.local(self.root, "knos-record")
        return self._store

    def _last(self) -> tuple[int, str]:
        es = self.entries()
        return (es[-1]["seq"], es[-1]["hash"]) if es else (-1, GENESIS)

    def _line(self, kind: str, payload: dict, claim, domain) -> dict:
        seq, prev = self._last()
        e = {"v": 1, "seq": seq + 1, "ts": int(time.time()), "kind": kind, "tier": TIERS.get(kind, "COLD"),
             "claim": claim, "domain": domain, "payload": payload, "prev": prev}
        e["hash"] = hashlib.sha256(_canon(e)).hexdigest()
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(e, sort_keys=True) + "\n")
        return e

    def append(self, kind, payload, *, claim=None, domain="", root=None) -> dict:
        e = self._line(kind, payload, claim, domain)
        self.store.journal(evaluated={"kind": kind, "claim": claim}, acted=payload, extra={"hash": e["hash"], "seq": e["seq"]})
        return e

    def claim(self, claim_id, payload, *, domain="", root=None) -> dict:
        self.store.put("record_claim", claim_id, payload)
        return self._line("claim", payload, claim_id, domain)

    def paper(self, ref_id, payload, *, root=None) -> dict:
        self.store.set_reference(ref_id, payload, kind="paper")
        return self._line("paper", payload, ref_id, "")

    def entries(self, root=None) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def verify(self, root=None, **_kw) -> dict:
        """Each line parses, its seq is the next one, its prev is the line before's hash (genesis first), its hash is
        the sha256 of the rest of it, its tier matches its kind; and the Merkle root over the hashes."""
        problems, hashes, prev = [], [], GENESIS
        lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        for n, raw in enumerate(lines):
            try:
                e = json.loads(raw)
                body = {k: v for k, v in e.items() if k != "hash"}
                ok = (e["seq"] == n and e["prev"] == prev and hashlib.sha256(_canon(body)).hexdigest() == e["hash"]
                      and e["tier"] == TIERS.get(e["kind"], "COLD") and isinstance(e["payload"], dict))
            except (ValueError, KeyError, TypeError):
                ok, e = False, {"hash": ""}
            if not ok:
                problems.append(n)
            prev = e.get("hash", "")
            hashes.append(prev if re.fullmatch(r"[0-9a-f]{64}", prev or "") else GENESIS)
        return {"ok": not problems, "entries": len(lines), "broken": problems, "merkle_root": merkle_root(hashes)}


class Recorder:
    """The loop's one door to the record."""

    def __init__(self, root: Path, claim_id: str, use_knos_record: bool = True):
        self.root = Path(root)
        self.claim_id = claim_id
        self.api = None
        if use_knos_record:
            try:
                from knos import record as api  # type: ignore[attr-defined]
                if all(hasattr(api, n) for n in ("append", "claim", "paper", "verify")):
                    self.api = api
            except ImportError:
                pass
        self.local = None if self.api else LocalRecord(self.root)
        self.backend = "knos.record" if self.api else LocalRecord.backend
        self.written: list[dict] = []

    def _do(self, fn: str, *a, **kw) -> dict:
        target = self.api or self.local
        e = getattr(target, fn)(*a, root=self.root, **kw)
        self.written.append(e)
        return e

    def claim(self, payload: dict) -> dict:
        return self._do("claim", self.claim_id, sanitize(payload), domain=DOMAIN)

    def paper(self, ref_id: str, payload: dict) -> dict:
        return self._do("paper", ref_id, sanitize(payload))

    def event(self, kind: str, payload: dict) -> dict:
        return self._do("append", kind, sanitize(payload), claim=self.claim_id, domain=DOMAIN)

    def verify(self) -> dict:
        got = (self.api or self.local).verify(self.root)
        if isinstance(got, dict) and "merkle_root" not in got:
            hashes = [e.get("hash", "") for e in self.written if isinstance(e, dict) and e.get("hash")]
            got = dict(got, merkle_root_of_this_run=merkle_root(hashes))
        return got

    def anchor(self, keypair=None, send=None) -> dict:
        """Anchor through knos.record (devnet). Never raises: a failure is reported, so the run's summary is written."""
        if not self.api or not hasattr(self.api, "anchor"):
            return {"anchored": False, "why": "knos.record.anchor is not installed"}
        try:
            got = self.api.anchor(self.root, keypair=keypair, send=send)
        except Exception as why:  # noqa: BLE001 - AnchorError, RecordError, a missing keypair, the network
            return {"anchored": False, "why": f"{type(why).__name__}: {str(why)[:200]}"}
        if got is None:
            return {"anchored": False, "why": "nothing pending"}
        return {"anchored": True, "tx": got.get("payload", {}).get("tx"), "root": got.get("payload", {}).get("root"),
                "seq": got.get("seq")}
