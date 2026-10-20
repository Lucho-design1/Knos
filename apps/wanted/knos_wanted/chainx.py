"""Solana programs Knos uses where they act, on devnet, sent by this server's relayer (it pays; nobody else signs):

  badge(...)        a Token-2022 track-record badge per verified milestone, minted to the maker: NonTransferable (it
                    cannot be sold), MetadataPointer + TokenMetadata on the mint (name, symbol, uri: the milestone),
                    MintCloseAuthority, and GroupMemberPointer + TokenGroupMember in the project's group mint
                    (GroupPointer + TokenGroup), so a project's badges are one group. The maker's account is its
                    Token-2022 associated token account (ImmutableOwner by construction).
  log_leaf(...)     a compressed track-record log: an SPL Account Compression concurrent merkle tree (depth 14, buffer
                    64), one leaf per attestation (the leaf is the sha256 of the attestation's address and milestone).
  memo(...)         a Memo after every release: "knos release <signature> brief sha256:<h> criteria sha256:<h>".
  rent_returned(sig) the lamports the release's closed accounts gave back, read from the transaction's own meta.
  sns_owner(name)   the owner of a .sol name (Name Service: the name account under the .sol root), when a project names one.
  price(pair)       a Pyth price (Hermes, no account), for a milestone that states a value in another currency.
  evm_verify(...)   an EVM-signed attestation (a lab instrument, a sensor) verified by Solana's Secp256k1 precompile in
                    a transaction: a wrong signature fails the transaction, so success is the proof.
State (the group mints, the tree, the badges) is kept beside the other server state (escrow._state_dir()).
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import threading
import urllib.request
from pathlib import Path

from . import escrow

TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ATA = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM = "11111111111111111111111111111111"
MEMO = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
COMPRESSION = "cmtDvXumGCrqC1Age74AVPhSRVXJMd8PJS91L8KbNCK"
NOOP = "noopb9bkMVfRPU8AsbpTUg8AQkHtKwMYZiFUjNRtMmV"
SECP256K1 = "KeccakSecp256k11111111111111111111111111111"
NAME_PROGRAM = "namesLPneVptA9Z5rqUDD9tMTWEJwofgaYwp8cawRkX"
SOL_TLD = "58PwtjSDuFHuUkYjH9BYnnQKHfwo9reZhC2zMJv9JPkx"
HERMES = "https://hermes.pyth.network/v2/updates/price/latest"
PYTH_IDS = {"EUR/USD": "a995d00bb36a63cef7fd2c287dc105fc8f3d93779f062f09551b0af3e81ec30b",
            "GBP/USD": "84c2dde9633d93d1bcad84e7dc41c9d56578b7ec52fabedc1f335d673df0a7c1",
            "SOL/USD": "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
            "BTC/USD": "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
            "ETH/USD": "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace"}
DEPTH, BUFFER = 14, 64
_lock = threading.Lock()


def _pk(s):
    from solders.pubkey import Pubkey
    return s if not isinstance(s, str) else Pubkey.from_string(s)


def _dir() -> Path:
    d = escrow._state_dir() / "valley" / "chainx"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state(name: str) -> dict:
    f = _dir() / f"{name}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def _keep(name: str, d: dict) -> None:
    (_dir() / f"{name}.json").write_text(json.dumps(d, indent=1), encoding="utf-8")


def _payer():
    from . import preorder
    return preorder.relayer()


def _ix(program: str, data: bytes, metas: list[tuple]):
    from solders.instruction import AccountMeta, Instruction
    return Instruction(_pk(program), data, [AccountMeta(_pk(k), s, w) for k, s, w in metas])


def _disc(name: str) -> bytes:
    return hashlib.sha256(name.encode()).digest()[:8]


def _s(text: str) -> bytes:
    b = text.encode()
    return struct.pack("<I", len(b)) + b


def _create(payer, new, space: int, lamports: int, owner: str):
    from solders.system_program import CreateAccountParams, create_account
    return create_account(CreateAccountParams(from_pubkey=payer, to_pubkey=new, lamports=lamports, space=space, owner=_pk(owner)))


# ---- Token-2022 badges ----------------------------------------------------------------------------------------------
BASE, TYPE = 165, 1                    # an extended mint: the base account padded to 165 bytes, then the account type byte


def _tlv(*lens: int) -> int:
    return BASE + TYPE + sum(4 + n for n in lens)


def _group_mint(led, pid: str, title: str) -> str:
    """The project's group mint (GroupPointer + TokenGroup), made once: its badges are the group's members."""
    from solders.keypair import Keypair
    st = _state("groups")
    if pid in st:
        return st[pid]
    payer, mint = _payer(), Keypair()
    space = _tlv(64)
    lamports = led.rent(space + 4 + 80)
    ixs = [_create(payer.pubkey(), mint.pubkey(), space, lamports, TOKEN22),
           _ix(TOKEN22, bytes([40, 0]) + bytes(payer.pubkey()) + bytes(mint.pubkey()), [(mint.pubkey(), False, True)]),
           _ix(TOKEN22, bytes([20, 0]) + bytes(payer.pubkey()) + bytes([0]), [(mint.pubkey(), False, True)]),
           _ix(TOKEN22, _disc("spl_token_group_interface:initialize_token_group") + bytes(payer.pubkey()) + struct.pack("<Q", 1024),
               [(mint.pubkey(), False, True), (mint.pubkey(), False, False), (payer.pubkey(), True, False)])]
    sig = led.send(ixs, payer, [payer, mint])
    st[pid] = str(mint.pubkey())
    _keep("groups", st)
    _keep(f"group-{pid}", {"mint": str(mint.pubkey()), "signature": sig, "title": title[:80]})
    return st[pid]


def badge(pid: str, title: str, key: str, name: str, maker_wallet: str, uri: str, led=None) -> dict:
    """One non-transferable badge of a verified milestone, minted to the maker, a member of the project's group."""
    from solders.keypair import Keypair
    led = led or escrow.ledger()
    with _lock:
        done = _state("badges")
        k = f"{pid}:{key}:{maker_wallet}"
        if k in done:
            return done[k]
        group = _group_mint(led, pid, title)
        payer, mint, owner = _payer(), Keypair(), _pk(maker_wallet)
        meta_name, symbol = f"Knos: {name}"[:32], "KNOSV"
        meta_len = 32 + 32 + 4 + len(meta_name.encode()) + 4 + len(symbol) + 4 + len(uri.encode()) + 4
        space = _tlv(32, 0, 64, 64)
        lamports = led.rent(space + (4 + 72) + (4 + meta_len))
        ata = _ata(owner, mint.pubkey())
        ixs = [_create(payer.pubkey(), mint.pubkey(), space, lamports, TOKEN22),
               _ix(TOKEN22, bytes([25, 1]) + bytes(payer.pubkey()), [(mint.pubkey(), False, True)]),                 # MintCloseAuthority
               _ix(TOKEN22, bytes([32]), [(mint.pubkey(), False, True)]),                                           # NonTransferable
               _ix(TOKEN22, bytes([39, 0]) + bytes(payer.pubkey()) + bytes(mint.pubkey()), [(mint.pubkey(), False, True)]),   # MetadataPointer
               _ix(TOKEN22, bytes([41, 0]) + bytes(payer.pubkey()) + bytes(mint.pubkey()), [(mint.pubkey(), False, True)]),   # GroupMemberPointer
               _ix(TOKEN22, bytes([20, 0]) + bytes(payer.pubkey()) + bytes([0]), [(mint.pubkey(), False, True)]),   # InitializeMint2
               _ix(TOKEN22, _disc("spl_token_metadata_interface:initialize_account") + _s(meta_name) + _s(symbol) + _s(uri),
                   [(mint.pubkey(), False, True), (payer.pubkey(), False, False), (mint.pubkey(), False, False), (payer.pubkey(), True, False)]),
               _ix(TOKEN22, _disc("spl_token_group_interface:initialize_member"),
                   [(mint.pubkey(), False, True), (mint.pubkey(), False, False), (payer.pubkey(), True, False), (_pk(group), False, True),
                    (payer.pubkey(), True, False)]),
               _ix(ATA, bytes([1]), [(payer.pubkey(), True, True), (ata, False, True), (owner, False, False), (mint.pubkey(), False, False),
                                     (_pk(SYSTEM), False, False), (_pk(TOKEN22), False, False)]),
               _ix(TOKEN22, bytes([7]) + struct.pack("<Q", 1), [(mint.pubkey(), False, True), (ata, False, True), (payer.pubkey(), True, False)])]
        sig = led.send(ixs, payer, [payer, mint])
        row = {"mint": str(mint.pubkey()), "account": str(ata), "owner": maker_wallet, "group": group, "signature": sig,
               "name": meta_name, "uri": uri, "extensions": ["NonTransferable", "MetadataPointer", "TokenMetadata", "MintCloseAuthority",
                                                             "GroupMemberPointer", "TokenGroupMember", "ImmutableOwner (the ATA)"],
               "explorer": escrow.explorer(str(mint.pubkey()), "address")}
        done[k] = row
        _keep("badges", done)
        return row


def _ata(owner, mint):
    from solders.pubkey import Pubkey
    return Pubkey.find_program_address([bytes(owner), bytes(_pk(TOKEN22)), bytes(mint)], _pk(ATA))[0]


def badges_of(wallet: str) -> list[dict]:
    return [v for v in _state("badges").values() if v["owner"] == wallet]


# ---- the compressed track-record log --------------------------------------------------------------------------------
def tree_size(depth: int = DEPTH, buffer: int = BUFFER) -> int:
    """The concurrent merkle tree's account: its 56-byte header, then sequence, active index and buffer size (24),
    `buffer` change logs (root, path, index + padding), and the rightmost proof (path, leaf, index + padding)."""
    return 56 + 24 + buffer * (32 + 32 * depth + 8) + (32 * depth + 32 + 8)


def _tree(led) -> str:
    from solders.keypair import Keypair
    st = _state("tree")
    if st.get("tree"):
        return st["tree"]
    payer, tree = _payer(), Keypair()
    size = tree_size()
    ixs = [_create(payer.pubkey(), tree.pubkey(), size, led.rent(size), COMPRESSION),
           _ix(COMPRESSION, _disc("global:init_empty_merkle_tree") + struct.pack("<II", DEPTH, BUFFER),
               [(tree.pubkey(), False, True), (payer.pubkey(), True, False), (_pk(NOOP), False, False)])]
    sig = led.send(ixs, payer, [payer, tree])
    _keep("tree", {"tree": str(tree.pubkey()), "signature": sig, "depth": DEPTH, "buffer": BUFFER, "leaves": 0})
    return str(tree.pubkey())


def log_leaf(text: str, led=None) -> dict:
    led = led or escrow.ledger()
    with _lock:
        tree = _tree(led)
        payer = _payer()
        leaf = hashlib.sha256(text.encode()).digest()
        sig = led.send([_ix(COMPRESSION, _disc("global:append") + leaf, [(tree, False, True), (payer.pubkey(), True, False), (_pk(NOOP), False, False)])], payer)
        st = _state("tree")
        st["leaves"] = st.get("leaves", 0) + 1
        _keep("tree", st)
        return {"tree": tree, "leaf": leaf.hex(), "index": st["leaves"] - 1, "signature": sig}


# ---- memo, rent, names, prices, EVM signatures -------------------------------------------------------------------------
def memo(text: str, led=None) -> str:
    led = led or escrow.ledger()
    payer = _payer()
    return led.send([_ix(MEMO, text.encode()[:500], [(payer.pubkey(), True, False)])], payer)


def rent_returned(signature: str, url: str | None = None) -> dict | None:
    """The lamports the transaction's closed accounts returned: the accounts whose balance went to 0, and who gained."""
    from knos import chain
    url = url or escrow.ledger().url
    t = chain.call(url, "getTransaction", [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    if not t:
        return None
    keys = t["transaction"]["message"]["accountKeys"] + (t["meta"].get("loadedAddresses") or {}).get("writable", []) + \
        (t["meta"].get("loadedAddresses") or {}).get("readonly", [])
    pre, post = t["meta"]["preBalances"], t["meta"]["postBalances"]
    closed = [(keys[i], pre[i]) for i in range(len(pre)) if pre[i] > 0 and post[i] == 0]
    return {"closed": [{"account": k, "lamports": v} for k, v in closed], "returned_lamports": sum(v for _, v in closed),
            "returned_sol": sum(v for _, v in closed) / 1e9, "fee_lamports": t["meta"]["fee"]}


def sns_owner(name: str, url: str | None = None) -> dict:
    """A .sol name's owner, read from the Name Service account (sha256 of the hashed-name prefix and the name)."""
    from solders.pubkey import Pubkey

    from knos import chain
    label = name.lower().removesuffix(".sol").strip()
    if not label or len(label) > 60 or not all(c.isalnum() or c in "-_" for c in label):
        raise ValueError("name: a .sol name such as knos.sol")
    hashed = hashlib.sha256(("SPL Name Service" + label).encode()).digest()
    acct = Pubkey.find_program_address([hashed, bytes(32), bytes(_pk(SOL_TLD))], _pk(NAME_PROGRAM))[0]
    got = chain.call(url or escrow.ledger().url, "getAccountInfo", [str(acct), {"encoding": "base64"}])
    v = (got or {}).get("value")
    if not v:
        return {"name": label + ".sol", "account": str(acct), "owner": None, "registered": False}
    data = base64.b64decode(v["data"][0])
    return {"name": label + ".sol", "account": str(acct), "owner": str(Pubkey.from_bytes(data[32:64])), "registered": True}


def price(pair: str, opener=None) -> dict:
    """The latest Pyth price of a pair (Hermes, the public price service): price, confidence, publish time."""
    pid = PYTH_IDS.get(pair.upper())
    if not pid:
        raise ValueError(f"pair: one of {', '.join(PYTH_IDS)}")
    req = urllib.request.Request(f"{HERMES}?ids[]={pid}&parsed=true", headers={"User-Agent": "knos"})
    with (opener or urllib.request.urlopen)(req, timeout=20) as r:
        p = json.loads(r.read())["parsed"][0]["price"]
    scale = 10 ** int(p["expo"])
    return {"pair": pair.upper(), "price": int(p["price"]) * scale, "confidence": int(p["conf"]) * scale, "publish_time": p["publish_time"],
            "source": "Pyth (Hermes)", "feed": pid}


def secp256k1_ix(eth_address: bytes, signature: bytes, recovery_id: int, message: bytes):
    """Solana's Secp256k1 precompile: one signature, all offsets inside this instruction (index 0 = itself)."""
    head = 1 + 11
    addr_o, sig_o = head, head + 20
    msg_o = sig_o + 65
    data = bytes([1]) + struct.pack("<HBHBHHB", sig_o, 0, addr_o, 0, msg_o, len(message), 0) + eth_address + signature + bytes([recovery_id]) + message
    return _ix(SECP256K1, data, [])


def evm_verify(eth_address: str, signature_hex: str, message: str, led=None) -> dict:
    """Verify an EVM-signed attestation on Solana: the precompile recovers the signer of keccak256(message) and
    compares it with eth_address; the transaction fails if they differ."""
    led = led or escrow.ledger()
    addr = bytes.fromhex(eth_address.lower().removeprefix("0x"))
    sig = bytes.fromhex(signature_hex.lower().removeprefix("0x"))
    if len(addr) != 20 or len(sig) != 65:
        raise ValueError("eth_address: 20 bytes; signature: 65 bytes (r, s, v)")
    v = sig[64]
    rid = v - 27 if v >= 27 else v
    payer = _payer()
    s = led.send([secp256k1_ix(addr, sig[:64], rid, message.encode()), _ix(MEMO, b"knos evm attestation verified", [(payer.pubkey(), True, False)])], payer)
    return {"verified": True, "signature": s, "signer": "0x" + addr.hex(), "by": "Solana's Secp256k1 precompile",
            "explorer": escrow.explorer(s)}
