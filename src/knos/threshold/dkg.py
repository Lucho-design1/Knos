"""FROST distributed key generation (RFC 9591 / frost-ed25519 keys::dkg, no trusted dealer) between the referee hosts.

Each party is its own process with its own secrets; the parties talk only through a RELAY (a mailbox that sees public
packages and ciphertexts, never a secret):

    r0  each party announces its transport key (Ed25519, signs everything it relays) and an X25519 key
    r1  each party's DKG round-1 package (public: its commitment and proof of knowledge), signed
    r2  each party's DKG round-2 packages, one per other party, each ENCRYPTED to that party
        (X25519 + HKDF-SHA256 + ChaCha20-Poly1305, associated data = the run, sender, recipient), signed
    r3  each party's resulting group key, signed: every party must report the same one

A party writes its OWN share record (KeyPackage + transport secret) to its own path, 0600. `pin` (optional): the
transport keys a party expects for the others (cross-host: exchanged out of band); without it the first r0
announcement per party is used, which is only acceptable when every party runs on one operator's machine.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import GROUP_KIND, HOSTS, MAX, MIN, SHARE_KIND, FrostError, auth_ok, b58, canon, run


class DirRelay:
    """The relay as a directory (one operator's machine; also what tests use)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, run_id: str, rnd: str, sender: int, body: dict, sig: str) -> None:
        d = self.root / run_id / rnd
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{sender}.json"
        if f.exists():
            raise FrostError(f"{rnd}: party {sender} already posted")
        tmp = d / f".{sender}.tmp"
        tmp.write_text(json.dumps({"body": body, "sig": sig}), encoding="utf-8")
        os.replace(tmp, f)

    def get(self, run_id: str, rnd: str) -> dict:
        d = self.root / run_id / rnd
        out = {}
        for f in sorted(d.glob("*.json")) if d.is_dir() else ():
            out[int(f.stem)] = json.loads(f.read_text(encoding="utf-8"))
        return out


def _wait(relay, run_id: str, rnd: str, n: int, timeout: float, poll: float) -> dict:
    end = time.time() + timeout
    while True:
        got = relay.get(run_id, rnd)
        if len(got) >= n:
            return got
        if time.time() > end:
            raise FrostError(f"DKG {rnd}: {len(got)} of {n} parties answered before the timeout")
        time.sleep(poll)


def _sign(kp, rnd: str, run_id: str, pid: int, body) -> str:
    import hashlib
    msg = hashlib.sha256(b"knos3:referee-frost:" + canon({"what": "dkg-" + rnd, "session": run_id, "id": pid, "body": body})).digest()
    return str(kp.sign_message(msg))


def _box_key(priv, peer_pub_hex: str, run_id: str, a: int, b: int) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    shared = priv.exchange(X25519PublicKey.from_public_bytes(bytes.fromhex(peer_pub_hex)))
    lo, hi = sorted((a, b))
    return HKDF(hashes.SHA256(), 32, salt=None, info=f"knos3:referee-frost:dkg:{run_id}:{lo}:{hi}".encode()).derive(shared)


def _seal(key: bytes, aad: bytes, plain: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce = os.urandom(12)
    return (nonce + ChaCha20Poly1305(key).encrypt(nonce, plain, aad)).hex()


def _open(key: bytes, aad: bytes, sealed: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    raw = bytes.fromhex(sealed)
    return ChaCha20Poly1305(key).decrypt(raw[:12], raw[12:], aad)


def party(pid: int, relay, run_id: str, out: str | Path, *, pin: dict | None = None, n: int = MAX, t: int = MIN,
          timeout: float = 600, poll: float = 0.2) -> dict:
    """Run one party of the DKG to the end; write its share record to `out`. Returns its PUBLIC result."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from solders.keypair import Keypair
    if pid not in range(1, n + 1):
        raise FrostError(f"party: 1..{n}")
    tkp, xpriv = Keypair(), X25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization
    xpub = xpriv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    body0 = {"transport_key": str(tkp.pubkey()), "x25519": xpub, "host": HOSTS.get(pid, str(pid))}
    relay.put(run_id, "r0", pid, body0, _sign(tkp, "r0", run_id, pid, body0))
    r0 = _wait(relay, run_id, "r0", n, timeout, poll)
    hosts = {}
    for j, m in r0.items():
        tk = m["body"]["transport_key"]
        if pin and str(j) in pin and pin[str(j)] != tk:
            raise FrostError(f"party {j} announced a transport key other than the pinned one")
        hosts[str(j)] = {"host": m["body"]["host"], "transport_key": tk, "x25519": m["body"]["x25519"]}
    grp = {"hosts": hosts}

    def check(rnd, msgs):
        for j, m in msgs.items():
            if not auth_ok(grp, j, "dkg-" + rnd, run_id, m["body"], m["sig"]):
                raise FrostError(f"DKG {rnd}: party {j}'s message is not signed by its transport key")
        for j, m in r0.items():
            if not auth_ok(grp, j, "dkg-r0", run_id, m["body"], m["sig"]):
                raise FrostError(f"DKG r0: party {j}'s announcement is not self-signed")
    check("r0", r0)
    one = run("dkg1", {"id": pid, "max": n, "min": t})
    body1 = {"package": one["package"]}
    relay.put(run_id, "r1", pid, body1, _sign(tkp, "r1", run_id, pid, body1))
    r1 = _wait(relay, run_id, "r1", n, timeout, poll)
    check("r1", r1)
    others1 = {str(j): m["body"]["package"] for j, m in r1.items() if j != pid}
    two = run("dkg2", {"secret": one["secret"], "packages": others1})
    sealed = {}
    for j, pkg in two["packages"].items():
        k = _box_key(xpriv, hosts[j]["x25519"], run_id, pid, int(j))
        sealed[j] = _seal(k, f"{run_id}:{pid}:{j}".encode(), json.dumps(pkg).encode())
    body2 = {"to": sealed}
    relay.put(run_id, "r2", pid, body2, _sign(tkp, "r2", run_id, pid, body2))
    r2 = _wait(relay, run_id, "r2", n, timeout, poll)
    check("r2", r2)
    mine = {}
    for j, m in r2.items():
        if j == pid:
            continue
        k = _box_key(xpriv, hosts[str(j)]["x25519"], run_id, j, pid)
        mine[str(j)] = json.loads(_open(k, f"{run_id}:{j}:{pid}".encode(), m["body"]["to"][str(pid)]))
    three = run("dkg3", {"secret": two["secret"], "round1": others1, "round2": mine})
    body3 = {"group_key": three["group_key"], "public": three["public"]}
    relay.put(run_id, "r3", pid, body3, _sign(tkp, "r3", run_id, pid, body3))
    r3 = _wait(relay, run_id, "r3", n, timeout, poll)
    check("r3", r3)
    if len({m["body"]["group_key"] for m in r3.values()}) != 1:
        raise FrostError("DKG: the parties computed different group keys; nothing is usable")
    share = {"v": 1, "kind": SHARE_KIND, "id": pid, "host": HOSTS.get(pid, str(pid)), "run": run_id, "min": t, "max": n,
             "group_key": b58(three["group_key"]), "group_key_hex": three["group_key"], "key_package": three["key_package"],
             "public": three["public"], "transport_key": str(tkp.pubkey()), "transport_secret": str(tkp),
             "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cluster": "devnet",
             "note": "SECRET: one FROST key share of Knos's devnet referee group. Keep it only on its own host."}
    out = Path(out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(out), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(share, f)
    return {"id": pid, "group_key": share["group_key"], "transport_key": share["transport_key"]}


def group_record(relay, run_id: str, n: int = MAX, t: int = MIN) -> dict:
    """The PUBLIC group record from the relay (r0 transport keys, r3 public key package), for config/referee-frost.json."""
    r0, r3 = relay.get(run_id, "r0"), relay.get(run_id, "r3")
    if len(r3) != n or len({m["body"]["group_key"] for m in r3.values()}) != 1:
        raise FrostError("the DKG did not finish with one group key")
    gk = next(iter(r3.values()))["body"]["group_key"]
    return {"v": 1, "kind": GROUP_KIND, "scheme": "FROST(Ed25519, SHA-512), RFC 9591, frost-ed25519 3.0.0", "run": run_id,
            "min": t, "max": n, "group_key": b58(gk), "group_key_hex": gk, "public": next(iter(r3.values()))["body"]["public"],
            "hosts": {str(j): {"host": m["body"]["host"], "transport_key": m["body"]["transport_key"]} for j, m in sorted(r0.items())},
            "keygen": "distributed key generation, no dealer (knos.threshold.dkg); three separate processes",
            "cluster": "devnet", "program": "FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4",
            "panel": f"1:{b58(gk)}", "test": True}
