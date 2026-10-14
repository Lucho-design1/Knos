"""One-transaction RS256 verification (v0.3.29). docs/reference/PLATFORM.md has the measured numbers.

knos-oidc's Step instruction does `squarings` of the 16 squarings of s^65537 mod n per call. A build of knos-oidc
for sBPF v2 does its arithmetic on 64-bit limbs (programs-v2/knos_oidc/src/rsa64.rs: the PQR instructions
make a 64 x 64 -> 128-bit product two instructions), so ONE Step(16) verifies a 2048-bit GitHub token inside one
transaction's 1,400,000 compute units. A build for sBPF v0 (what devnet runs today) or
v3 (whose Agave 4.4 form has no 128-bit multiply) still needs two: Step(8), Step(8).

    KNOS_OIDC_VERIFY   two (default: the old two-step plan, what every deployed build takes)
                       one (one Step for a 2048-bit key: only against a build for sBPF v2)
                       auto (ask the build: `plan(bits, "auto", elf)` reads its sBPF version)

A v1 transaction (SIMD-0385, 4,096 bytes) carries a token of the usual size whole: `one_transaction_ixs` gives the
Write and the Step(16) that verify it in ONE transaction (knos.chain.Ledger.send(..., v1=True)).
"""
from __future__ import annotations

import os

from solders.instruction import Instruction
from solders.pubkey import Pubkey

MODES = ("two", "one", "auto")
ENV = "KNOS_OIDC_VERIFY"
TWO_STEP = {2048: [8, 8], 4096: [2, 3, 3, 3, 4, 1]}      # the plans every build takes (knos.settle.oidc.step_plan)
ONE_STEP = {2048: [16], 4096: [4, 4, 4, 4]}               # a build for sBPF v2: see PLATFORM.md for the 4096-bit numbers


def mode(value: str | None = None) -> str:
    word = (value if value is not None else os.environ.get(ENV, "") or "two").strip().lower()
    if word not in MODES:
        raise ValueError(f"{ENV} must be one of {', '.join(MODES)}; got {word!r}")
    return word


def sbpf_version(elf: bytes | None) -> int | None:
    """The sBPF version of a program's ELF: its e_flags (byte 48 of an ELF64 header; 0 = v0 ... 3 = v3). A deployed
    program's ProgramData account holds 45 bytes of header before the ELF: pass `programdata[45:]`."""
    if not elf or len(elf) < 52 or elf[:4] != b"\x7fELF":
        return None
    return int.from_bytes(elf[48:52], "little")


def fast(elf: bytes | None) -> bool:
    """Whether this build of knos-oidc does its RSA on 64-bit limbs (built for sBPF v2: the v3 of Agave 4.4 has no 128-bit multiply, so a v3 build keeps 32-bit limbs)."""
    v = sbpf_version(elf)
    return v == 2


def plan(bits: int, how: str | None = None, elf: bytes | None = None) -> list[int]:
    """Squarings per Step transaction for a key of `bits`. `how`: two, one or auto (KNOS_OIDC_VERIFY); auto needs the
    build's `elf` and falls back to the two-step plan without it."""
    if bits not in TWO_STEP:
        raise ValueError(f"knos-oidc takes 2048- and 4096-bit keys, not {bits}")
    m = mode(how)
    if m == "one" or (m == "auto" and fast(elf)):
        return list(ONE_STEP[bits])
    return list(TWO_STEP[bits])


def one_transaction_ixs(payer: Pubkey, jwt: str | bytes, key: Pubkey, program: Pubkey | None = None) -> list[Instruction]:
    """Write (the whole token, one chunk) and Step(16): what verifies a token under a 2048-bit key in ONE v1
    transaction, against a build for sBPF v2. The caller adds the compute-unit limit (the v1 message
    carries it: knos.chain.message_v1)."""
    from ..settle.v2 import oidc
    raw = jwt if isinstance(jwt, bytes) else jwt.encode()
    tid = oidc.token_id(raw)
    pid = program or oidc.OIDC_ID
    write = oidc.write_ixs(payer, tid, raw, pid)
    # oidc.write_ixs cuts every CHUNK bytes for legacy transactions; one v1 transaction takes the token whole
    from solders.instruction import AccountMeta
    whole = Instruction(pid, b"\x00" + tid + len(raw).to_bytes(2, "little") + (0).to_bytes(2, "little") + raw,
                        [AccountMeta(payer, True, True), AccountMeta(oidc.token_pda(payer, tid, pid), False, True),
                         AccountMeta(oidc.SYSTEM, False, False)])
    assert write and bytes(write[0].data)[:35] == bytes(whole.data)[:35]
    return [whole, oidc.step_ix(payer, tid, key, 16, pid)]


def fits_v1(ixs: list[Instruction], payer: Pubkey) -> bool:
    from .. import chain
    return chain.tx_size(ixs, payer, v1=True) <= chain.MAX_V1_BYTES


def es256_v1_ixs(payer: Pubkey, key_account: Pubkey, jwt: str | bytes, key: bytes, program: Pubkey | None = None) -> list[Instruction]:
    """The secp256r1 precompile and VerifyEs256 (knos.settle.v2.oidc.verify_es256_ixs) for a token whose signing input
    is longer than the 780 bytes a legacy transaction leaves: in ONE v1 transaction (4,096 bytes) it may be about
    3,600 (`fits_v1` says). The program takes the message from the precompile's own data, whatever its length."""
    import hashlib

    from solders.instruction import AccountMeta

    from ..settle.v2 import oidc
    text = (jwt.decode() if isinstance(jwt, bytes) else jwt).strip()
    parts = text.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("a compact token is three parts with two dots")
    short = f"{parts[0][:4]}.{parts[1][:4]}.{parts[2]}"           # es256_parts checks the signature; the input's length is ours
    _, signature = oidc.es256_parts(short)
    message = f"{parts[0]}.{parts[1]}".encode()
    pid = program or oidc.OIDC_ID
    token = oidc.token_pda(payer, hashlib.sha256(message).digest(), pid)
    return [oidc.secp256r1_ix(key, signature, message),
            Instruction(pid, b"\x0f", [AccountMeta(payer, True, True), AccountMeta(token, False, True), AccountMeta(key_account, False, False),
                                       AccountMeta(oidc.SYSTEM, False, False), AccountMeta(oidc.SYSVAR_INSTRUCTIONS, False, False)])]
