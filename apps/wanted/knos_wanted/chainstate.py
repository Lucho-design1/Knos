"""Projects that survive a redeploy, kept on Solana devnet with what Knos already has.

The app's state directory is not on a disk (Render rebuilds it on every deploy), so each saved project is also written,
off the request's path, into its own account of the SPL Record program (recr1L3PCGKLbckBqMNcJhuuyU1zgo8nBhfLVsJNwr5,
deployed on devnet), whose authority is this server's relayer. On start, when the state directory holds no project,
one getProgramAccounts call (filtered on that authority) reads every record back and the projects are written again.
No paid service and no new account: the relayer pays devnet rent and fees, test SOL only.

A record's data, after the program's 33-byte header (version 1, authority 32):
    b"KNOS1" | kind length u8 | kind | key length u8 | key | written at, ns u64 | body length u32 | zlib(JSON)
A project grows: a body that no longer fits its account goes into a new, larger account, and the old one is closed (its
rent comes back). When two records name the same project (a close that did not land), the newest "written at" wins.

On only when KNOS_STATE_ON_CHAIN=1 (the hosted app); tests and local runs keep the plain directory.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import struct
import sys
import threading
import time
import zlib

RECORD = "recr1L3PCGKLbckBqMNcJhuuyU1zgo8nBhfLVsJNwr5"
HEADER = 33                        # RecordData: version u8 + authority 32 (WRITABLE_START_INDEX)
MAGIC = b"KNOS1"
CHUNK = 800                        # bytes of data per Write transaction (a transaction holds 1,232)
KINDS = ("projects", "traces", "pages", "outside", "orders", "amc",     # an order's document is what releases or refunds it
         "agentkeys")                       # an agent key's caps and counters (only the secret's sha256): a restart keeps them
_q: "queue.Queue[tuple[str, str, dict]]" = queue.Queue()
_index: dict[tuple[str, str], tuple[str, int]] = {}      # (kind, key) -> (record account, capacity)
_lock = threading.Lock()
_worker: threading.Thread | None = None


def on() -> bool:
    return os.environ.get("KNOS_STATE_ON_CHAIN") == "1"


def encode(kind: str, key: str, obj: dict, at_ns: int | None = None) -> bytes:
    body = zlib.compress(json.dumps(obj, separators=(",", ":"), default=str).encode(), 9)
    k, n = kind.encode(), key.encode()
    return (MAGIC + bytes([len(k)]) + k + bytes([len(n)]) + n + struct.pack("<QI", at_ns or time.time_ns(), len(body)) + body)


def decode(data: bytes) -> tuple[str, str, int, dict] | None:
    """(kind, key, written at, object) from a record's data (after the header), or None when it is not one of ours."""
    if not data.startswith(MAGIC):
        return None
    i = len(MAGIC)
    kl = data[i]
    kind = data[i + 1:i + 1 + kl].decode()
    i += 1 + kl
    nl = data[i]
    key = data[i + 1:i + 1 + nl].decode()
    i += 1 + nl
    at, size = struct.unpack_from("<QI", data, i)
    i += 12
    return kind, key, at, json.loads(zlib.decompress(data[i:i + size]))


def _ix(program: str, data: bytes, metas: list[tuple]):
    from solders.instruction import AccountMeta, Instruction
    from solders.pubkey import Pubkey
    pk = lambda s: s if not isinstance(s, str) else Pubkey.from_string(s)  # noqa: E731
    return Instruction(pk(program), data, [AccountMeta(pk(k), s, w) for k, s, w in metas])


def _write_ixs(record, authority, payload: bytes) -> list[list]:
    return [[_ix(RECORD, bytes([1]) + struct.pack("<QI", off, len(payload[off:off + CHUNK])) + payload[off:off + CHUNK],
                 [(record, False, True), (authority, True, False)])] for off in range(0, len(payload), CHUNK)]


def write(kind: str, key: str, obj: dict, led=None, payer=None) -> str:
    """Write one object to its record account (a new, larger one when it outgrew the old, which is then closed)."""
    from solders.keypair import Keypair
    from solders.system_program import CreateAccountParams, create_account

    from . import escrow, preorder
    led = led or escrow.ledger()
    payer = payer or preorder.relayer()
    payload = encode(kind, key, obj)
    with _lock:
        have = _index.get((kind, key))
    if have and have[1] >= len(payload):
        account = have[0]
        for ixs in _write_ixs(account, payer.pubkey(), payload):
            led.send(ixs, payer)
        return account
    cap = max(len(payload) * 2, 1024)                        # room to grow before the next move
    new = Keypair()
    first, *rest = _write_ixs(new.pubkey(), payer.pubkey(), payload)
    led.send([create_account(CreateAccountParams(from_pubkey=payer.pubkey(), to_pubkey=new.pubkey(), lamports=led.rent(HEADER + cap),
                                                 space=HEADER + cap, owner=_pk(RECORD))),
              _ix(RECORD, bytes([0]), [(new.pubkey(), False, True), (payer.pubkey(), False, False)]), *first], payer, [payer, new])
    for ixs in rest:
        led.send(ixs, payer)
    with _lock:
        _index[(kind, key)] = (str(new.pubkey()), cap)
    if have:                                                 # the old, smaller record: closed, its rent back to the payer
        try:
            led.send([_ix(RECORD, bytes([3]), [(have[0], False, True), (payer.pubkey(), True, False), (payer.pubkey(), False, True)])], payer)
        except Exception as why:  # noqa: BLE001 - a record left behind is older; the newest one wins on restore
            print(f"knos chainstate: old record {have[0][:8]} not closed: {type(why).__name__}", file=sys.stderr, flush=True)
    return str(new.pubkey())


def _pk(s: str):
    from solders.pubkey import Pubkey
    return Pubkey.from_string(s)


def records(url: str, authority: str) -> list[tuple[str, int, tuple[str, str, int, dict]]]:
    """Every record of ours on chain: (account, capacity, (kind, key, written at, object))."""
    from knos import chain
    got = chain.call(url, "getProgramAccounts", [RECORD, {"encoding": "base64", "commitment": "confirmed",
                                                          "filters": [{"memcmp": {"offset": 1, "bytes": authority}}]}], timeout=60)
    out = []
    for a in got or []:
        raw = base64.b64decode(a["account"]["data"][0])
        try:
            rec = decode(raw[HEADER:])
        except (ValueError, KeyError, struct.error, zlib.error, UnicodeDecodeError):
            rec = None
        if rec and rec[0] in KINDS:
            out.append((a["pubkey"], len(raw) - HEADER, rec))
    return out


def restore(save, led=None, payer=None) -> int:
    """On start: read every record and save the newest of each project again. Returns how many were restored."""
    from . import escrow, preorder
    led = led or escrow.ledger()
    payer = payer or preorder.relayer()
    newest: dict[tuple[str, str], tuple[int, str, int, dict]] = {}
    for account, cap, (kind, key, at, obj) in records(led.url, str(payer.pubkey())):
        if (kind, key) not in newest or at > newest[(kind, key)][0]:
            newest[(kind, key)] = (at, account, cap, obj)
    with _lock:
        for (kind, key), (_at, account, cap, _obj) in newest.items():
            _index[(kind, key)] = (account, cap)
    for (kind, key), (_at, _account, _cap, obj) in newest.items():
        save(kind, key, obj)
    return len(newest)


def queue_save(kind: str, key: str, obj: dict) -> None:
    """After a save: copy the object to chain, off the request's path (the latest version of a key wins)."""
    global _worker
    if not on() or kind not in KINDS:
        return
    _q.put((kind, key, json.loads(json.dumps(obj, default=str))))
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain, daemon=True, name="knos-chainstate")
            _worker.start()


def _drain() -> None:
    while True:
        kind, key, obj = _q.get()
        latest = {(kind, key): obj}
        while not _q.empty():                              # coalesce: only the newest version of each key is written
            k2, n2, o2 = _q.get_nowait()
            latest[(k2, n2)] = o2
        for (k, n), o in latest.items():
            for attempt in range(3):                       # bounded retries
                try:
                    write(k, n, o)
                    break
                except Exception as why:  # noqa: BLE001
                    print(f"knos chainstate: {k}/{n} not written ({attempt + 1}/3): {type(why).__name__}: {str(why)[:160]}",
                          file=sys.stderr, flush=True)
                    time.sleep(2 * (attempt + 1))
