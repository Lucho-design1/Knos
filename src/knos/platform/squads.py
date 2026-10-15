"""Squads v4 spending limits for the treasury: a bounded key may pay set costs from the fee vault without a vote each time.

Knos's fees land in a Squads vault (config/fees.yaml `treasury.fee_owner`); moving anything out takes a proposal and
the members' votes. Running a research market has small recurring costs that should not wait for a vote each: refunding
a faucet, paying a lab's sample fee the referee approved, topping up the relay's fee payer. A Squads v4 spending limit
lets named keys (they "don't have to be members of the multisig") move at most `amount` of one mint per period, only
to listed destinations (empty: anywhere), from one vault (IDL squads_multisig_program 2.1.0, MultisigAddSpendingLimitArgs
and ConfigAction::AddSpendingLimit; programs/squads_multisig_program/src/state/spending_limit.rs; github.com/Squads-Protocol/v4,
read 14 Oct 2026). For an autonomous multisig (no config authority, as both of Knos's are) the limit is added by a
config transaction the members vote on: config_transaction_create -> proposal_create -> proposal_approve (threshold) ->
config_transaction_execute, the last with the new SpendingLimit PDA, the rent payer and the system program.

This module builds those instructions (Anchor: 8-byte sha256("global:<name>") discriminator + Borsh), reads the
accounts back, and writes the plan for the founder. It never signs with a member key: `plan` returns unsigned
instructions and the exact steps; the devnet proof in scripts/capabilities_devnet.py runs the same instructions on a
multisig made of fresh test keys of its own, never Knos's.

PDAs (programs/squads_multisig_program/src/state/seeds.rs): multisig ["multisig","multisig",create_key];
transaction ["multisig",multisig,"transaction",index u64]; proposal [... ,"proposal"]; vault
["multisig",multisig,"vault",index u8]; spending limit ["multisig",multisig,"spending_limit",create_key];
program config ["multisig","program_config"].
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

PROGRAM = Pubkey.from_string("SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf")
SYSTEM = Pubkey.from_string("11111111111111111111111111111111")
PERIODS = {"one-time": 0, "day": 1, "week": 2, "month": 3}
INITIATE, VOTE, EXECUTE = 1, 2, 4
ALL = INITIATE | VOTE | EXECUTE


def disc(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


def account_disc(name: str) -> bytes:
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]


def _pda(seeds: list[bytes]) -> Pubkey:
    return Pubkey.find_program_address(seeds, PROGRAM)[0]


def multisig_pda(create_key: Pubkey) -> Pubkey:
    return _pda([b"multisig", b"multisig", bytes(create_key)])


def program_config_pda() -> Pubkey:
    return _pda([b"multisig", b"program_config"])


def transaction_pda(multisig: Pubkey, index: int) -> Pubkey:
    return _pda([b"multisig", bytes(multisig), b"transaction", index.to_bytes(8, "little")])


def proposal_pda(multisig: Pubkey, index: int) -> Pubkey:
    return _pda([b"multisig", bytes(multisig), b"transaction", index.to_bytes(8, "little"), b"proposal"])


def vault_pda(multisig: Pubkey, index: int = 0) -> Pubkey:
    return _pda([b"multisig", bytes(multisig), b"vault", bytes([index])])


def spending_limit_pda(multisig: Pubkey, create_key: Pubkey) -> Pubkey:
    return _pda([b"multisig", bytes(multisig), b"spending_limit", bytes(create_key)])


def _vec_keys(keys) -> bytes:
    keys = list(keys)
    return len(keys).to_bytes(4, "little") + b"".join(bytes(k) for k in keys)


def _opt_str(s: str | None) -> bytes:
    return b"\x00" if s is None else b"\x01" + len(s.encode()).to_bytes(4, "little") + s.encode()


def add_spending_limit_action(create_key: Pubkey, mint: Pubkey, amount: int, period: str, members, destinations=(), vault_index: int = 0) -> bytes:
    """ConfigAction::AddSpendingLimit (variant 4). `mint` Pubkey.default() means SOL."""
    if amount <= 0:
        raise ValueError("a spending limit's amount is positive")
    return (bytes([4]) + bytes(create_key) + bytes([vault_index]) + bytes(mint) + amount.to_bytes(8, "little") + bytes([PERIODS[period]])
            + _vec_keys(members) + _vec_keys(destinations))


def multisig_create_v2_ix(create_key: Pubkey, creator: Pubkey, treasury: Pubkey, members: list[tuple[Pubkey, int]], threshold: int,
                          time_lock: int = 0, config_authority: Pubkey | None = None) -> Instruction:
    data = (disc("multisig_create_v2") + (b"\x00" if config_authority is None else b"\x01" + bytes(config_authority))
            + threshold.to_bytes(2, "little") + len(members).to_bytes(4, "little") + b"".join(bytes(k) + bytes([m]) for k, m in members)
            + time_lock.to_bytes(4, "little") + b"\x00" + _opt_str(None))
    return Instruction(PROGRAM, data, [AccountMeta(program_config_pda(), False, False), AccountMeta(treasury, False, True),
                                       AccountMeta(multisig_pda(create_key), False, True), AccountMeta(create_key, True, False),
                                       AccountMeta(creator, True, True), AccountMeta(SYSTEM, False, False)])


def config_transaction_create_ix(multisig: Pubkey, index: int, creator: Pubkey, rent_payer: Pubkey, actions: list[bytes], memo: str | None = None) -> Instruction:
    data = disc("config_transaction_create") + len(actions).to_bytes(4, "little") + b"".join(actions) + _opt_str(memo)
    return Instruction(PROGRAM, data, [AccountMeta(multisig, False, True), AccountMeta(transaction_pda(multisig, index), False, True),
                                       AccountMeta(creator, True, False), AccountMeta(rent_payer, True, True), AccountMeta(SYSTEM, False, False)])


def proposal_create_ix(multisig: Pubkey, index: int, creator: Pubkey, rent_payer: Pubkey, draft: bool = False) -> Instruction:
    return Instruction(PROGRAM, disc("proposal_create") + index.to_bytes(8, "little") + bytes([draft]),
                       [AccountMeta(multisig, False, False), AccountMeta(proposal_pda(multisig, index), False, True),
                        AccountMeta(creator, True, False), AccountMeta(rent_payer, True, True), AccountMeta(SYSTEM, False, False)])


def proposal_approve_ix(multisig: Pubkey, index: int, member: Pubkey, memo: str | None = None) -> Instruction:
    return Instruction(PROGRAM, disc("proposal_approve") + _opt_str(memo),
                       [AccountMeta(multisig, False, False), AccountMeta(member, True, True), AccountMeta(proposal_pda(multisig, index), False, True)])


def config_transaction_execute_ix(multisig: Pubkey, index: int, member: Pubkey, rent_payer: Pubkey, spending_limits=()) -> Instruction:
    return Instruction(PROGRAM, disc("config_transaction_execute"),
                       [AccountMeta(multisig, False, True), AccountMeta(member, True, False), AccountMeta(proposal_pda(multisig, index), False, True),
                        AccountMeta(transaction_pda(multisig, index), False, False), AccountMeta(rent_payer, True, True),
                        AccountMeta(SYSTEM, False, False), *[AccountMeta(s, False, True) for s in spending_limits]])


def spending_limit_use_ix(multisig: Pubkey, member: Pubkey, spending_limit: Pubkey, destination: Pubkey, amount: int, decimals: int,
                          mint: Pubkey, token_program: Pubkey, vault_index: int = 0, memo: str | None = None) -> Instruction:
    """Move `amount` of an SPL `mint` from the vault's token account to `destination`'s, within the limit. Anchor's
    absent optional accounts are passed as the program id; for a token limit all four token accounts are given."""
    from ..money.x402_upto import ata
    vault = vault_pda(multisig, vault_index)
    return Instruction(PROGRAM, disc("spending_limit_use") + amount.to_bytes(8, "little") + bytes([decimals]) + _opt_str(memo),
                       [AccountMeta(multisig, False, False), AccountMeta(member, True, False), AccountMeta(spending_limit, False, True),
                        AccountMeta(vault, False, True), AccountMeta(destination, False, True), AccountMeta(PROGRAM, False, False),
                        AccountMeta(mint, False, False), AccountMeta(ata(vault, mint, token_program), False, True),
                        AccountMeta(ata(destination, mint, token_program), False, True), AccountMeta(token_program, False, False)])


@dataclass(frozen=True)
class Multisig:
    create_key: Pubkey
    config_authority: Pubkey
    threshold: int
    time_lock: int
    transaction_index: int
    stale_transaction_index: int
    members: list


def read_multisig(data: bytes) -> Multisig:
    d = bytes(data)
    if d[:8] != account_disc("Multisig"):
        raise ValueError("not a Squads v4 multisig account")
    i = 8
    ck, ca = Pubkey.from_bytes(d[i:i + 32]), Pubkey.from_bytes(d[i + 32:i + 64])
    i += 64
    thr, tl = int.from_bytes(d[i:i + 2], "little"), int.from_bytes(d[i + 2:i + 6], "little")
    ti, sti = int.from_bytes(d[i + 6:i + 14], "little"), int.from_bytes(d[i + 14:i + 22], "little")
    i += 22
    i += 33 if d[i] == 1 else 1          # rent_collector Option<Pubkey>
    i += 1                               # bump
    n = int.from_bytes(d[i:i + 4], "little")
    i += 4
    members = [(Pubkey.from_bytes(d[i + 33 * k:i + 33 * k + 32]), d[i + 33 * k + 32]) for k in range(n)]
    return Multisig(ck, ca, thr, tl, ti, sti, members)


@dataclass(frozen=True)
class SpendingLimit:
    multisig: Pubkey
    create_key: Pubkey
    vault_index: int
    mint: Pubkey
    amount: int
    period: str
    remaining: int
    last_reset: int
    members: list
    destinations: list


def read_spending_limit(data: bytes) -> SpendingLimit:
    d = bytes(data)
    if d[:8] != account_disc("SpendingLimit"):
        raise ValueError("not a Squads v4 spending limit account")
    i = 8
    ms, ck, vi, mint = Pubkey.from_bytes(d[i:i + 32]), Pubkey.from_bytes(d[i + 32:i + 64]), d[i + 64], Pubkey.from_bytes(d[i + 65:i + 97])
    i += 97
    amount, period = int.from_bytes(d[i:i + 8], "little"), {v: k for k, v in PERIODS.items()}[d[i + 8]]
    remaining, reset = int.from_bytes(d[i + 9:i + 17], "little"), int.from_bytes(d[i + 17:i + 25], "little", signed=True)
    i += 25 + 1                          # bump
    def keys(at):
        n = int.from_bytes(d[at:at + 4], "little")
        return [Pubkey.from_bytes(d[at + 4 + 32 * k:at + 36 + 32 * k]) for k in range(n)], at + 4 + 32 * n
    members, i = keys(i)
    dests, _ = keys(i)
    return SpendingLimit(ms, ck, vi, mint, amount, period, remaining, reset, members, dests)


def plan(multisig: Pubkey, ms: Multisig, create_key: Pubkey, mint: Pubkey, amount: int, period: str, spenders, destinations,
         proposer: Pubkey, vault_index: int = 0) -> dict:
    """The unsigned instructions and the steps that add one spending limit to an autonomous multisig. Nothing is sent:
    the proposer and the voting members sign on their own machines (or with scripts/governance.mjs)."""
    index = ms.transaction_index + 1
    action = add_spending_limit_action(create_key, mint, amount, period, spenders, destinations, vault_index)
    limit = spending_limit_pda(multisig, create_key)
    ixs = {"create": config_transaction_create_ix(multisig, index, proposer, proposer, [action], "knos: spending limit"),
           "propose": proposal_create_ix(multisig, index, proposer, proposer),
           "execute": config_transaction_execute_ix(multisig, index, proposer, proposer, [limit])}
    return {"multisig": str(multisig), "vault": str(vault_pda(multisig, vault_index)), "transaction_index": index,
            "spending_limit": str(limit), "threshold": ms.threshold, "time_lock_s": ms.time_lock,
            "instructions": {k: {"program": str(v.program_id), "data_hex": bytes(v.data).hex(),
                                 "accounts": [[str(a.pubkey), a.is_signer, a.is_writable] for a in v.accounts]} for k, v in ixs.items()},
            "steps": [f"1. A member with Initiate creates config transaction {index} (AddSpendingLimit: {amount} units of {mint} per {period}, "
                      f"spenders {', '.join(map(str, spenders))}, destinations {', '.join(map(str, destinations)) or 'any'}) and its proposal.",
                      f"2. {ms.threshold} members with Vote approve proposal {index}.",
                      f"3. After the time lock ({ms.time_lock} s from approval) a member with Execute runs config_transaction_execute "
                      f"with the spending limit {limit}, the rent payer and the system program.",
                      f"4. Read it back: knos.platform.squads.read_spending_limit on the account {limit}."]}
