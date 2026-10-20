"""Track records: one Solana Attestation Service attestation per verified milestone, to the maker's wallet and to each
referee's (the FROST group key), on devnet. GET /api/track?wallet= lists a wallet's attestations, each read back from
the chain (an attestation that is not on chain is not shown as one).

  credential  ["credential", this server's devnet key, "knos-track"]
  schema      ["schema", credential, "milestone-verified", 1]: project, milestone, role, criteria_sha256, release, wallet
  attestation ["attestation", credential, schema, nonce]: nonce = sha256(project|milestone|attempt|role|wallet)
"""
from __future__ import annotations

import hashlib
import json
import threading
import time

from . import escrow

CREDENTIAL, SCHEMA = "knos-track", "milestone-verified"
FIELDS = ["project", "milestone", "role", "criteria_sha256", "release", "wallet"]
LAYOUT = bytes([12] * len(FIELDS))
_lock = threading.Lock()


def _dir():
    d = escrow._state_dir() / "valley" / "track"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ids(authority):
    from knos.platform import sas
    cred = sas.credential_pda(authority, CREDENTIAL)
    return cred, sas.schema_pda(cred, SCHEMA)


def _setup(led, key) -> list[str]:
    from knos.platform import sas
    cred, schema = _ids(key.pubkey())
    sent = []
    if led.account(cred) is None:
        sent.append(led.send([sas.create_credential_ix(key.pubkey(), key.pubkey(), CREDENTIAL, [key.pubkey()])], key))
    if led.account(schema) is None:
        sent.append(led.send([sas.create_schema_ix(key.pubkey(), key.pubkey(), cred, SCHEMA, "A Knos milestone verified and paid", LAYOUT,
                                                   FIELDS)], key))
    return sent


def nonce(pid: str, key: str, attempt: str, role: str, wallet: str):
    from solders.pubkey import Pubkey
    return Pubkey.from_bytes(hashlib.sha256(f"{pid}|{key}|{attempt}|{role}|{wallet}".encode()).digest())


def attest(pid: str, key: str, attempt: str, subjects: list[tuple[str, str]], criteria: str, release: str, led=None) -> list[dict]:
    """One attestation per (role, wallet): the maker and every referee of the verified milestone."""
    from knos.platform import sas
    led = led or escrow.ledger()
    k = escrow.demo_key()
    out = []
    with _lock:
        _setup(led, k)
        cred, schema = _ids(k.pubkey())
        for role, wallet in subjects:
            n = nonce(pid, key, attempt, role, wallet)
            att = sas.attestation_pda(cred, schema, n)
            sig = None
            if led.account(att) is None:
                data = sas.encode(LAYOUT, [pid, key, role, criteria or "", release or "", wallet])
                sig = led.send([sas.create_attestation_ix(k.pubkey(), k.pubkey(), cred, schema, n, data)], k)
            row = {"project": pid, "milestone": key, "attempt": attempt, "role": role, "wallet": wallet, "attestation": str(att),
                   "signature": sig, "criteria_sha256": criteria, "release": release, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            f = _dir() / f"{hashlib.sha256(wallet.encode()).hexdigest()[:24]}.json"
            rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
            if not any(r["attestation"] == row["attestation"] for r in rows):
                rows.append(row)
                f.write_text(json.dumps(rows, indent=1), encoding="utf-8")
            out.append(row)
    return out


def record(wallet: str, led=None) -> dict:
    """A wallet's track record: its attestations, each read back from the chain."""
    from solders.pubkey import Pubkey

    from knos.platform import sas
    Pubkey.from_string(wallet)
    led = led or escrow.ledger()
    f = _dir() / f"{hashlib.sha256(wallet.encode()).hexdigest()[:24]}.json"
    rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    cred, schema = _ids(escrow.demo_key().pubkey())
    shown = []
    for r in rows:
        data = led.account(Pubkey.from_string(r["attestation"]))
        if data is None:
            continue
        a = sas.read_attestation(data)
        fields = sas.decode(LAYOUT, tuple(FIELDS), a.data)
        if a.credential != cred or a.schema != schema or fields.get("wallet") != wallet:
            continue
        shown.append({**r, "on_chain": fields, "explorer": escrow.explorer(r["attestation"], "address")})
    from . import chainx
    return {"wallet": wallet, "verified_milestones": len(shown), "attestations": shown, "credential": str(cred), "schema": str(schema),
            "badges": chainx.badges_of(wallet),
            "program": str(sas.PROGRAM), "cluster": "devnet"}
