"""Solana Attestation Service attestations READ as inputs: "pay when credential C has attested R about subject S".

Knos already writes its acceptance receipts as SAS attestations (scripts/sas_receipt.mjs). This reads the other way: an
attestation someone else signed becomes a condition Knos checks before it counts evidence or releases money. A lab
accreditation body attests that a lab is accredited, a core facility attests that a sample was run, a panel of
reviewers attests a result: none of them needs GitHub or CI, only a key that their credential authorizes.

What a verifier must check, from the service's own README (github.com/solana-foundation/solana-attestation-service,
"Verifying an attestation from another program", read 14 Oct 2026), and what `check` does, in that order:
  1. the account is at the address derived from ["attestation", credential, schema, subject] under program
     22zoJMtdu4tQc2PzL74ZUT7FrwgB1Udec8DdW4yw4BdG (the issuers' convention: the subject's wallet is the nonce);
  2. that program owns it, and its first byte is the attestation discriminator (2);
  3. its credential and schema are the ones the order names ("the credential you pass is the issuer you trust: anyone
     can create a credential and schema, so the check is only as strong as that choice");
  4. expiry is 0 or later than the cluster's clock (never the local clock);
  5. its signer is still among the credential's authorized signers (Knos's own stricter rule: a signer the issuer has
     since removed no longer vouches; the README does not require it).
A closed attestation has no account, which is how revocation shows. The data is decoded with the schema's own layout.

Layouts are the program's (program/src/state/{credential,schema,attestation}.rs, same day):
  Credential  0 | authority 32 | name (u32 len + bytes) | authorized_signers (u32 count + 32 each)
  Schema      1 | credential 32 | name | description | layout (u32 len + type codes) | field_names (u32 len + bytes) | paused u8 | version u8
  Attestation 2 | nonce 32 | credential 32 | schema 32 | data (u32 len + bytes) | signer 32 | expiry i64 | token_account 32
The create_* builders (instruction discriminators 0, 1 and 6 of the IDL) exist so a test issuer can be stood up on devnet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

PROGRAM = Pubkey.from_string("22zoJMtdu4tQc2PzL74ZUT7FrwgB1Udec8DdW4yw4BdG")
SYSTEM = Pubkey.from_string("11111111111111111111111111111111")
CREDENTIAL, SCHEMA, ATTESTATION = 0, 1, 2
# the schema type codes (program/src/state/schema.rs SchemaDataTypes) Knos decodes; others are refused, not guessed
TYPES = {0: ("u8", 1), 1: ("u16", 2), 2: ("u32", 4), 3: ("u64", 8), 4: ("u128", 16), 5: ("i8", 1), 6: ("i16", 2), 7: ("i32", 4),
         8: ("i64", 8), 9: ("i128", 16), 10: ("bool", 1), 11: ("char", 4), 12: ("string", None), 13: ("vec_u8", None)}


@dataclass(frozen=True)
class Credential:
    authority: Pubkey
    name: str
    signers: tuple[Pubkey, ...]


@dataclass(frozen=True)
class Schema:
    credential: Pubkey
    name: str
    description: str
    layout: bytes
    fields: tuple[str, ...]
    paused: bool
    version: int


@dataclass(frozen=True)
class Attestation:
    nonce: Pubkey
    credential: Pubkey
    schema: Pubkey
    data: bytes
    signer: Pubkey
    expiry: int
    token_account: Pubkey


def _pda(seeds: list[bytes]) -> Pubkey:
    return Pubkey.find_program_address(seeds, PROGRAM)[0]


def credential_pda(authority: Pubkey, name: str) -> Pubkey:
    return _pda([b"credential", bytes(authority), name.encode()])


def schema_pda(credential: Pubkey, name: str, version: int = 1) -> Pubkey:
    return _pda([b"schema", bytes(credential), name.encode(), bytes([version])])


def attestation_pda(credential: Pubkey, schema: Pubkey, nonce: Pubkey) -> Pubkey:
    return _pda([b"attestation", bytes(credential), bytes(schema), bytes(nonce)])


class _R:
    def __init__(self, data: bytes, at: int = 1):
        self.d, self.i = bytes(data), at

    def take(self, n: int) -> bytes:
        if self.i + n > len(self.d):
            raise ValueError("the account is shorter than its layout")
        out, self.i = self.d[self.i:self.i + n], self.i + n
        return out

    def u32(self) -> int:
        return int.from_bytes(self.take(4), "little")

    def key(self) -> Pubkey:
        return Pubkey.from_bytes(self.take(32))

    def vec(self) -> bytes:
        return self.take(self.u32())


def read_credential(data: bytes) -> Credential:
    if not data or data[0] != CREDENTIAL:
        raise ValueError("not a credential account")
    r = _R(data)
    authority, name = r.key(), r.vec().decode()
    return Credential(authority, name, tuple(r.key() for _ in range(r.u32())))


def read_schema(data: bytes) -> Schema:
    if not data or data[0] != SCHEMA:
        raise ValueError("not a schema account")
    r = _R(data)
    cred, name, desc, layout = r.key(), r.vec().decode(), r.vec().decode(), r.vec()
    names_raw = _R(r.vec(), 0)
    names = []
    while names_raw.i < len(names_raw.d):
        names.append(names_raw.vec().decode())
    return Schema(cred, name, desc, layout, tuple(names), r.take(1) == b"\x01", r.take(1)[0])


def read_attestation(data: bytes) -> Attestation:
    if not data or data[0] != ATTESTATION:
        raise ValueError("not an attestation account")
    r = _R(data)
    nonce, cred, schema, body, signer = r.key(), r.key(), r.key(), r.vec(), r.key()
    expiry = int.from_bytes(r.take(8), "little", signed=True)
    return Attestation(nonce, cred, schema, body, signer, expiry, r.key())


def decode(layout: bytes, names: tuple[str, ...], data: bytes) -> dict:
    """The attestation's data as {field name: value}, by the schema's layout. Refused when the bytes do not fit."""
    r, out = _R(data, 0), {}
    for i, code in enumerate(layout):
        if code not in TYPES:
            raise ValueError(f"schema type code {code} is not one Knos decodes")
        kind, size = TYPES[code]
        name = names[i] if i < len(names) else f"field{i}"
        if kind == "string":
            out[name] = r.vec().decode()
        elif kind == "vec_u8":
            out[name] = r.vec().hex()
        elif kind == "bool":
            out[name] = r.take(1) == b"\x01"
        elif kind == "char":
            out[name] = chr(int.from_bytes(r.take(4), "little"))
        else:
            out[name] = int.from_bytes(r.take(size), "little", signed=kind.startswith("i"))
    if r.i != len(r.d):
        raise ValueError("the data is longer than the schema's layout")
    return out


@dataclass
class Verdict:
    ok: bool
    why: str
    attestation: str
    fields: dict = field(default_factory=dict)
    expiry: int = 0
    signer: str = ""


def check(ledger, credential: Pubkey, schema: Pubkey, subject: Pubkey, now: int | None = None, expect: dict | None = None) -> Verdict:
    """Whether `credential` has attested about `subject` under `schema`, as the chain has it now. `expect`: field values
    the data must have (e.g. {"accredited": True}). `now`: the cluster's clock (ledger.now()) unless given."""
    addr = attestation_pda(credential, schema, subject)
    got = ledger.infos([addr, credential, schema])
    att_i, cred_i, schema_i = got
    if att_i is None:
        return Verdict(False, "no attestation: none was written for this subject, or it was closed (revoked)", str(addr))
    if att_i[0] != PROGRAM:
        return Verdict(False, f"the account at {addr} is not owned by the Solana Attestation Service", str(addr))
    try:
        att = read_attestation(att_i[1])
    except ValueError as why:
        return Verdict(False, str(why), str(addr))
    if att.credential != credential or att.schema != schema or att.nonce != subject:
        return Verdict(False, "the attestation names another credential, schema or subject", str(addr))
    t = ledger.now() if now is None else now
    if att.expiry != 0 and att.expiry <= t:
        return Verdict(False, f"the attestation expired at {att.expiry} (cluster clock {t})", str(addr), expiry=att.expiry, signer=str(att.signer))
    if cred_i is None or cred_i[0] != PROGRAM or schema_i is None or schema_i[0] != PROGRAM:
        return Verdict(False, "the credential or the schema is not an account of the Solana Attestation Service", str(addr))
    cred, sch = read_credential(cred_i[1]), read_schema(schema_i[1])
    if att.signer not in cred.signers:
        return Verdict(False, f"{att.signer} signed it but is no longer an authorized signer of the credential {cred.name!r}", str(addr))
    try:
        values = decode(sch.layout, sch.fields, att.data)
    except ValueError as why:
        return Verdict(False, f"the data does not fit the schema: {why}", str(addr))
    wrong = {k: v for k, v in (expect or {}).items() if values.get(k) != v}
    if wrong:
        return Verdict(False, "the attested data differs: " + ", ".join(f"{k} is {values.get(k)!r}, not {v!r}" for k, v in wrong.items()),
                       str(addr), values, att.expiry, str(att.signer))
    return Verdict(True, f"attested by {att.signer} under credential {cred.name!r}, schema {sch.name!r} v{sch.version}",
                   str(addr), values, att.expiry, str(att.signer))


# -- builders for a test issuer (the IDL's createCredential 0, createSchema 1, createAttestation 6) --------------------
def _s(text: str | bytes) -> bytes:
    b = text.encode() if isinstance(text, str) else bytes(text)
    return len(b).to_bytes(4, "little") + b


def create_credential_ix(payer: Pubkey, authority: Pubkey, name: str, signers: list[Pubkey]) -> Instruction:
    data = bytes([0]) + _s(name) + len(signers).to_bytes(4, "little") + b"".join(bytes(s) for s in signers)
    return Instruction(PROGRAM, data, [AccountMeta(payer, True, True), AccountMeta(credential_pda(authority, name), False, True),
                                       AccountMeta(authority, True, False), AccountMeta(SYSTEM, False, False)])


def create_schema_ix(payer: Pubkey, authority: Pubkey, credential: Pubkey, name: str, description: str, layout: bytes,
                     fields: list[str]) -> Instruction:
    data = bytes([1]) + _s(name) + _s(description) + _s(layout) + len(fields).to_bytes(4, "little") + b"".join(_s(f) for f in fields)
    return Instruction(PROGRAM, data, [AccountMeta(payer, True, True), AccountMeta(authority, True, False), AccountMeta(credential, False, False),
                                       AccountMeta(schema_pda(credential, name), False, True), AccountMeta(SYSTEM, False, False)])


def create_attestation_ix(payer: Pubkey, authority: Pubkey, credential: Pubkey, schema: Pubkey, nonce: Pubkey, data: bytes,
                          expiry: int = 0) -> Instruction:
    body = bytes([6]) + bytes(nonce) + _s(data) + expiry.to_bytes(8, "little", signed=True)
    return Instruction(PROGRAM, body, [AccountMeta(payer, True, True), AccountMeta(authority, True, False), AccountMeta(credential, False, False),
                                       AccountMeta(schema, False, False), AccountMeta(attestation_pda(credential, schema, nonce), False, True),
                                       AccountMeta(SYSTEM, False, False)])


def encode(layout: bytes, values: list) -> bytes:
    """The data bytes for `values` in the schema's layout (the inverse of `decode`), for a test issuer."""
    out = b""
    for code, v in zip(layout, values):
        kind, size = TYPES[code]
        if kind == "string":
            out += _s(v)
        elif kind == "vec_u8":
            out += _s(bytes(v))
        elif kind == "bool":
            out += b"\x01" if v else b"\x00"
        elif kind == "char":
            out += ord(v).to_bytes(4, "little")
        else:
            out += int(v).to_bytes(size, "little", signed=kind.startswith("i"))
    return out
