"""Squads v4 spending limits (knos.platform.squads): instruction bytes against the program's IDL 2.1.0, account
readers on bytes built here, and the founder's plan, which signs nothing. Keys are made in the test (synthetic)."""
from __future__ import annotations

import hashlib

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from knos.platform import squads as s


def test_anchor_discriminators_are_sha256_of_the_instruction_names():
    for name in ("config_transaction_create", "proposal_create", "proposal_approve", "config_transaction_execute", "spending_limit_use",
                 "multisig_create_v2"):
        assert s.disc(name) == hashlib.sha256(f"global:{name}".encode()).digest()[:8]


def test_the_add_spending_limit_action_is_variant_4_in_idl_order():
    ck, mint, spender, dest = (Keypair().pubkey() for _ in range(4))
    a = s.add_spending_limit_action(ck, mint, 5_000_000, "day", [spender], [dest])
    assert a[0] == 4 and a[1:33] == bytes(ck) and a[33] == 0 and a[34:66] == bytes(mint)
    assert int.from_bytes(a[66:74], "little") == 5_000_000 and a[74] == s.PERIODS["day"]
    assert a[75:79] == (1).to_bytes(4, "little") and a[79:111] == bytes(spender) and a[111:115] == (1).to_bytes(4, "little")


def multisig_bytes(threshold: int, time_lock: int, index: int, members) -> bytes:
    return (s.account_disc("Multisig") + bytes(Keypair().pubkey()) + bytes(32) + threshold.to_bytes(2, "little") + time_lock.to_bytes(4, "little")
            + index.to_bytes(8, "little") + (0).to_bytes(8, "little") + b"\x00" + b"\xff" + len(members).to_bytes(4, "little")
            + b"".join(bytes(k) + bytes([m]) for k, m in members))


def test_the_plan_is_unsigned_instructions_and_the_founders_steps():
    members = [(Keypair().pubkey(), 7) for _ in range(3)]
    ms = s.read_multisig(multisig_bytes(2, 691_200, 9, members))
    assert ms.threshold == 2 and ms.time_lock == 691_200 and ms.transaction_index == 9 and ms.members == members
    msa, ck, mint, spender = (Keypair().pubkey() for _ in range(4))
    p = s.plan(msa, ms, ck, mint, 1_000_000, "week", [spender], [], members[0][0])
    assert p["transaction_index"] == 10 and p["spending_limit"] == str(s.spending_limit_pda(msa, ck))
    assert "691200 s" in p["steps"][2] and "2 members" in p["steps"][1]
    create = p["instructions"]["create"]
    assert bytes.fromhex(create["data_hex"])[:8] == s.disc("config_transaction_create")
    assert [a[0] for a in create["accounts"]][1] == str(s.transaction_pda(msa, 10))
    assert "signature" not in str(p)                                              # nothing is signed, by anyone


def test_spending_limit_use_names_the_vault_and_both_token_accounts():
    from knos.money.x402_upto import ata
    msa, member, limit, dest, mint = (Keypair().pubkey() for _ in range(5))
    tp = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
    ix = s.spending_limit_use_ix(msa, member, limit, dest, 3, 6, mint, tp)
    keys = [a.pubkey for a in ix.accounts]
    vault = s.vault_pda(msa)
    assert keys[3] == vault and keys[7] == ata(vault, mint, tp) and keys[8] == ata(dest, mint, tp) and keys[5] == s.PROGRAM
    assert ix.accounts[1].is_signer and bytes(ix.data)[8:16] == (3).to_bytes(8, "little") and bytes(ix.data)[16] == 6


def test_a_spending_limit_account_is_read_back():
    msa, ck, mint, m1, d1 = (Keypair().pubkey() for _ in range(5))
    raw = (s.account_disc("SpendingLimit") + bytes(msa) + bytes(ck) + b"\x00" + bytes(mint) + (5).to_bytes(8, "little") + b"\x01"
           + (2).to_bytes(8, "little") + (0).to_bytes(8, "little") + b"\xfe" + (1).to_bytes(4, "little") + bytes(m1) + (1).to_bytes(4, "little") + bytes(d1))
    sl = s.read_spending_limit(raw)
    assert sl.amount == 5 and sl.period == "day" and sl.remaining == 2 and sl.members == [m1] and sl.destinations == [d1]
