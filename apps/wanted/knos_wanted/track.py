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
    # the solvers' index (GET /api/solvers): which wallets have verified work, kept with the server's state on devnet so
    # it survives a redeploy; each listing reads the attestations back from the chain (record), never from this index
    from . import valley
    idx = valley._safe_load("pages", "solvers") or {"wallets": {}}
    for r in out:
        if r["role"] == "maker":
            idx["wallets"][r["wallet"]] = sorted(set(idx["wallets"].get(r["wallet"], []) + [r["attestation"]]))
    valley._save("pages", "solvers", idx)
    return out


def record(wallet: str, led=None) -> dict:
    """A wallet's track record: its attestations, each read back from the chain."""
    from solders.pubkey import Pubkey

    from knos.platform import sas
    Pubkey.from_string(wallet)
    led = led or escrow.ledger()
    f = _dir() / f"{hashlib.sha256(wallet.encode()).hexdigest()[:24]}.json"
    rows = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    # the local rows do not survive a redeploy; the solvers' index (kept on devnet) names every maker attestation, and
    # each is read back from the chain all the same
    from . import valley
    known = {r["attestation"] for r in rows}
    found = list(((valley._safe_load("pages", "solvers") or {}).get("wallets") or {}).get(wallet) or [])
    for p in valley._all("projects"):                # and each project's own record of its paid attempts
        for m in p.get("milestones") or []:
            for a in m.get("attempts") or []:
                found += [t["attestation"] for t in a.get("attestations") or [] if t.get("wallet") == wallet and t.get("attestation")]
    for att in found:
        if att not in known:
            known.add(att)
            rows.append({"attestation": att, "wallet": wallet})
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
        shown.append({**{k: fields.get(k) for k in ("project", "milestone", "role", "criteria_sha256", "release")}, **r,
                      "on_chain": fields, "explorer": escrow.explorer(r["attestation"], "address")})
    from . import chainx
    return {"wallet": wallet, "verified_milestones": len(shown), "attestations": shown, "credential": str(cred), "schema": str(schema),
            "badges": chainx.badges_of(wallet),
            "program": str(sas.PROGRAM), "cluster": "devnet"}


# ---- the shareable "Ready to fund" card (TASK-CHAMPION T2, status) ---------------------------------------------------
# A brief that passes Knos's Ready check is attested once on devnet, under the same credential, by its criteria hash:
#   schema ["schema", credential, "brief-ready", 1]: criteria_sha256, title, milestones, checked_at
#   attestation nonce = sha256("ready|" + criteria_sha256): the same brief is the same card, however often it is made
READY_SCHEMA, READY_FIELDS = "brief-ready", ["criteria_sha256", "title", "milestones", "checked_at"]
READY_LAYOUT = bytes([12] * len(READY_FIELDS))


def _ready_ids(authority):
    from knos.platform import sas
    cred = sas.credential_pda(authority, CREDENTIAL)
    return cred, sas.schema_pda(cred, READY_SCHEMA)


def _cards() -> dict:
    from . import valley
    return valley._safe_load("pages", "ready_cards") or {"cards": []}


def ready_card(brief: dict, led=None) -> dict:
    """Check the brief; if it is Ready, attest it on devnet (once per criteria hash) and return the card."""
    from solders.pubkey import Pubkey

    from knos import ready as kr
    from knos.platform import sas

    from . import valley
    r = kr.check(brief)
    if not r.get("ready"):
        return {"ready": False, "missing": r.get("missing") or [], "card": None}
    h = r["criteria_hash"]
    doc = _cards()
    have = next((c for c in doc["cards"] if c["criteria_sha256"] == h), None)
    if have:
        return {"ready": True, "card": have}
    led = led or escrow.ledger()
    k = escrow.demo_key()
    title = str((brief or {}).get("title") or "")[:120]
    n_ms = len((kr.clean(brief) or {}).get("milestones") or [])
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _lock:
        _setup(led, k)
        cred, schema = _ready_ids(k.pubkey())
        if led.account(schema) is None:
            led.send([sas.create_schema_ix(k.pubkey(), k.pubkey(), cred, READY_SCHEMA, "A brief that passed Knos's Ready check", READY_LAYOUT,
                                           READY_FIELDS)], k)
        nonce_pk = Pubkey.from_bytes(hashlib.sha256(f"ready|{h}".encode()).digest())
        att = sas.attestation_pda(cred, schema, nonce_pk)
        sig = None
        if led.account(att) is None:
            data = sas.encode(READY_LAYOUT, [h, title, str(n_ms), at])
            sig = led.send([sas.create_attestation_ix(k.pubkey(), k.pubkey(), cred, schema, nonce_pk, data)], k)
    card = {"criteria_sha256": h, "title": title, "milestones": n_ms, "checked_at": at, "attestation": str(att), "signature": sig,
            "explorer": escrow.explorer(str(att), "address"), "page": f"/ready/{h}", "cluster": "devnet"}
    doc["cards"] = [card] + [c for c in doc["cards"] if c["criteria_sha256"] != h][:199]
    valley._save("pages", "ready_cards", doc)
    return {"ready": True, "card": card}


def ready_card_get(h: str, led=None) -> dict:
    """A card as the chain holds it: shown only when its attestation is on devnet under this credential and schema."""
    from solders.pubkey import Pubkey

    from knos.platform import sas
    card = next((c for c in _cards()["cards"] if c["criteria_sha256"] == h), None)
    if not card:
        return {"found": False}
    led = led or escrow.ledger()
    data = led.account(Pubkey.from_string(card["attestation"]))
    if data is None:
        return {"found": False, "why": "the attestation is not on devnet"}
    a = sas.read_attestation(data)
    cred, schema = _ready_ids(escrow.demo_key().pubkey())
    fields = sas.decode(READY_LAYOUT, tuple(READY_FIELDS), a.data)
    if a.credential != cred or a.schema != schema or fields.get("criteria_sha256") != h:
        return {"found": False, "why": "the attestation does not match this card"}
    return {"found": True, "card": card, "on_chain": fields, "credential": str(cred), "schema": str(schema), "program": str(sas.PROGRAM)}


def ready_cards_summary() -> dict:
    cards = _cards()["cards"]
    return {"ready_cards_attested": len(cards), "latest": cards[0]["page"] if cards else None,
            "latest_attestation": cards[0]["explorer"] if cards else None, "cluster": "devnet"}
