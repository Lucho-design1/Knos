"""Just enough Ethereum to pay a lab over x402 `exact` on Base: keccak-256, secp256k1 signatures (RFC 6979, low s,
recoverable), addresses, EIP-712 typed data and the EIP-3009 TransferWithAuthorization that x402 `exact` on EVM signs.

Pure Python, no dependency (the Knos install has no Ethereum library). It signs only: it never sends a transaction and
never holds a key beyond the call. Checked by tests against published vectors (keccak-256 of "", the address of
private key 1, recover(sign(x)) == the signer).
"""
from __future__ import annotations

import hashlib
import hmac

# ---- keccak-256 (the original Keccak padding, not NIST SHA3) ----------------------------------------------------------
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
       0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
       0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
       0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
       0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _rol(x: int, n: int) -> int:
    n %= 64
    return ((x << n) | (x >> (64 - n))) & _M if n else x


def _f(a: list[list[int]]) -> None:
    for rc in _RC:
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        a[0][0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    msg = bytearray(data) + b"\x01"
    while len(msg) % rate:
        msg += b"\x00"
    msg[-1] |= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        block = msg[off:off + rate]
        for i in range(rate // 8):
            a[i % 5][i // 5] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _f(a)
    out = b"".join(a[i % 5][i // 5].to_bytes(8, "little") for i in range(4))
    return out[:32]


# ---- secp256k1 ----------------------------------------------------------------------------------------------------------
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    if p1[0] == p2[0] and (p1[1] + p2[1]) % P == 0:
        return None
    if p1 == p2:
        lam = 3 * p1[0] * p1[0] * pow(2 * p1[1], -1, P) % P
    else:
        lam = (p2[1] - p1[1]) * pow(p2[0] - p1[0], -1, P) % P
    x = (lam * lam - p1[0] - p2[0]) % P
    return x, (lam * (p1[0] - x) - p1[1]) % P


def _mul(k: int, pt=G):
    out, add = None, pt
    while k:
        if k & 1:
            out = _add(out, add)
        add = _add(add, add)
        k >>= 1
    return out


def _k(priv: int, h: bytes) -> int:
    """RFC 6979 deterministic nonce (HMAC-SHA256)."""
    x = priv.to_bytes(32, "big")
    h = (int.from_bytes(h, "big") % N).to_bytes(32, "big")          # bits2octets
    v, k = b"\x01" * 32, b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def sign_hash(priv: bytes, h: bytes) -> bytes:
    """65 bytes r || s || v (v = 27 + recovery id), low s, over a 32-byte hash."""
    d = int.from_bytes(priv, "big")
    if not 1 <= d < N or len(h) != 32:
        raise ValueError("a 32-byte private key in range and a 32-byte hash")
    z = int.from_bytes(h, "big")
    k = _k(d, h)
    R = _mul(k)
    r = R[0] % N
    s = pow(k, -1, N) * (z + r * d) % N
    rec = (R[1] & 1) | (2 if R[0] >= N else 0)
    if s > N // 2:
        s, rec = N - s, rec ^ 1
    return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27 + rec])


def recover(h: bytes, sig: bytes) -> str:
    """The address that signed `h`."""
    r, s, v = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:64], "big"), sig[64]
    rec = v - 27 if v >= 27 else v
    x = r + (N if rec & 2 else 0)
    y2 = (pow(x, 3, P) + 7) % P
    y = pow(y2, (P + 1) // 4, P)
    if (y & 1) != (rec & 1):
        y = P - y
    R = (x, y)
    z = int.from_bytes(h, "big")
    rinv = pow(r, -1, N)
    Q = _add(_mul(s * rinv % N, R), _mul((-z * rinv) % N))
    return _address_of(Q)


def _address_of(Q) -> str:
    raw = Q[0].to_bytes(32, "big") + Q[1].to_bytes(32, "big")
    return checksum("0x" + keccak256(raw)[-20:].hex())


def address(priv: bytes) -> str:
    return _address_of(_mul(int.from_bytes(priv, "big")))


def checksum(addr: str) -> str:
    """EIP-55 mixed-case checksum address."""
    a = addr.lower().removeprefix("0x")
    if len(a) != 40 or any(c not in "0123456789abcdef" for c in a):
        raise ValueError(f"not an address: {addr!r}")
    h = keccak256(a.encode()).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(h[i], 16) >= 8 else c for i, c in enumerate(a))


# ---- EIP-712 / EIP-3009 -----------------------------------------------------------------------------------------------
DOMAIN_TYPE = b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
TWA_TYPE = (b"TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,"
            b"bytes32 nonce)")


def _addr32(a: str) -> bytes:
    return bytes(12) + bytes.fromhex(a.lower().removeprefix("0x"))


def _u256(v: int) -> bytes:
    return int(v).to_bytes(32, "big")


def domain_separator(name: str, version: str, chain_id: int, contract: str) -> bytes:
    return keccak256(keccak256(DOMAIN_TYPE) + keccak256(name.encode()) + keccak256(version.encode()) + _u256(chain_id) + _addr32(contract))


def transfer_with_authorization_hash(auth: dict, *, name: str, version: str, chain_id: int, contract: str) -> bytes:
    """The EIP-712 digest of an EIP-3009 TransferWithAuthorization (what USDC checks, and what x402 `exact` on EVM signs)."""
    struct = keccak256(keccak256(TWA_TYPE) + _addr32(auth["from"]) + _addr32(auth["to"]) + _u256(int(auth["value"])) +
                       _u256(int(auth["validAfter"])) + _u256(int(auth["validBefore"])) +
                       bytes.fromhex(auth["nonce"].removeprefix("0x")))
    return keccak256(b"\x19\x01" + domain_separator(name, version, chain_id, contract) + struct)
