"""Per-claim accounts (knos.platform.claims): two tokens verified by two payers, or by one, share no writable account
but the payer; the 2.0 job path's per-mint vault is the one shared account, and orders do not use it."""
from __future__ import annotations

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from knos.platform import claims
from knos.settle.v2 import oidc, pay


def _verify_ixs(payer: Pubkey, jwt: bytes, key: Pubkey):
    tid = oidc.token_id(jwt)
    return [*oidc.write_ixs(payer, tid, jwt), oidc.step_ix(payer, tid, key, 16), oidc.close_ix(payer, tid)]


def test_two_tokens_share_no_writable_account_but_the_payer():
    a, b, key = Keypair().pubkey(), Keypair().pubkey(), Keypair().pubkey()
    by = {"a1": _verify_ixs(a, b"x" * 1500, key), "a2": _verify_ixs(a, b"y" * 1500, key), "b1": _verify_ixs(b, b"x" * 1500, key)}
    shared = claims.shared_writable(by)
    assert set(shared) == {a} and sorted(shared[a]) == ["a1", "a2"]
    assert claims.shared_writable(by, ignore=[a, b]) == {}
    assert key not in claims.writable(by["a1"])             # the key account is read, never written, by Step


def test_order_money_is_per_order_and_the_job_vault_is_per_mint():
    mint = Keypair().pubkey()
    o1, o2 = Keypair().pubkey(), Keypair().pubkey()
    assert pay.ov_pda(o1) != pay.ov_pda(o2)
    assert pay.vault_pda(mint) == pay.vault_pda(mint)       # the 2.0 job path: one vault per mint (PLATFORM.md)
    assert claims.per_block(1_400_000) == 8 and claims.per_block(0) == claims.ACCOUNT_UNITS_PER_BLOCK
