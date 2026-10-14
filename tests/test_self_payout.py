"""knos self: an accepted improvement pays its bounty on devnet, with the fee from the one fee config; every key is
named on the command line; mainnet is refused."""
from __future__ import annotations

import subprocess

import pytest

from knos.self import payout

TARGET = {"id": "mcp-cold-start", "bounty_usd": "1.00"}
SIG1, SIG2, SIG3 = "5" * 88, "4" * 88, "3" * 88


def test_the_plan_comes_from_the_fee_config():
    p = payout.plan(TARGET)
    assert (p["amount"], p["fee"], p["total"]) == (1_000_000, 50_000, 1_050_000)      # bounty line: 30 bps, floor 0.05
    assert p["treasury_owner"] == "4G3cznCnwCUPBCZwzKiLupjdgB5pSoCcGWNGuFv4TYFo" and p["fee_line"] == "fees.bounty"
    big = payout.plan({"id": "x", "bounty_usd": "100.00"})
    assert big["fee"] == 300_000                                                         # 30 bps of 100.00
    assert payout.ui(1_000_000) == "1.000000" and payout.ui(50_000) == "0.050000"


def _wallet(tmp_path, rpc="https://api.devnet.solana.com"):
    (tmp_path / "cli.yml").write_text(f'json_rpc_url: "{rpc}"\nkeypair_path: {tmp_path}/treasury.json\n')
    (tmp_path / "treasury.json").write_text("[]")
    return tmp_path


def test_execute_makes_two_transfers_with_every_key_named(tmp_path):
    calls = []
    transfer_sigs = iter([SIG1, SIG3])

    def runner(argv, **kw):
        calls.append(argv)
        if argv[0] == "solana-keygen":
            return subprocess.CompletedProcess(argv, 0, "3gQxtRxsuuicL7gkcoaGZwVtP8RverKwn1wGEpd3uYDM\n", "")
        if argv[3] == "account-info":
            return subprocess.CompletedProcess(argv, 1, "", "not found")
        sig = next(transfer_sigs) if argv[3] == "transfer" else SIG2
        return subprocess.CompletedProcess(argv, 0, f"Signature: {sig}\n", "")
    p = payout.plan(TARGET)
    mint = "4C6dtRowv5gGgdVxX3YdHmRwoD5vNt1W5wXGRcCvp3X1"
    got = payout.execute(p, wallet_dir=_wallet(tmp_path), payee="EK7H81j97oaupJijuzaK2WZvaLVKgJosbxyCiqWPupHs", mint=mint, runner=runner)
    assert got["payout_tx"] == SIG1 and got["fee_tx"] == SIG3 and got["fee_account_tx"] == SIG2
    assert got["fee_account"] == payout.fee_account(mint, p["treasury_owner"])
    spl = [c for c in calls if c[0] == "spl-token"]
    assert all("--config" in c for c in spl)
    for c in spl:
        if c[3] in ("transfer", "create-account"):
            assert "--fee-payer" in c
        if c[3] == "transfer":
            assert "--owner" in c
    assert spl[0][4:7] == [mint, "1.000000", "EK7H81j97oaupJijuzaK2WZvaLVKgJosbxyCiqWPupHs"]
    assert [c for c in spl if c[3] == "transfer"][-1][5] == "0.050000"


def test_mainnet_and_a_missing_wallet_are_refused(tmp_path):
    p = payout.plan(TARGET)
    with pytest.raises(payout.PayoutError, match="devnet"):
        payout.execute(p, wallet_dir=_wallet(tmp_path), payee="x", mint="y", rpc="https://api.mainnet-beta.solana.com")
    with pytest.raises(payout.PayoutError, match="wallet"):
        payout.execute(p, wallet_dir=tmp_path / "none", payee="x", mint="y")
    (tmp_path / "w").mkdir()
    w = _wallet(tmp_path / "w", "https://api.mainnet-beta.solana.com")
    with pytest.raises(payout.PayoutError, match="does not point"):
        payout.execute(p, wallet_dir=w, payee="x", mint="y")


def test_the_devnet_guard_reads_the_rpc_line_not_a_substring(tmp_path):
    (tmp_path / "cli.yml").write_text('# was https://api.devnet.solana.com\njson_rpc_url: "https://api.mainnet-beta.solana.com"\n')
    (tmp_path / "treasury.json").write_text("[]")
    with pytest.raises(payout.PayoutError, match="does not point"):
        payout.execute(payout.plan(TARGET), wallet_dir=tmp_path, payee="x", mint="y")


def test_a_failed_fee_transfer_says_what_was_already_sent(tmp_path):
    def runner(argv, **kw):
        if argv[0] == "solana-keygen":
            return subprocess.CompletedProcess(argv, 0, "3gQxtRxsuuicL7gkcoaGZwVtP8RverKwn1wGEpd3uYDM\n", "")
        if argv[3] == "account-info":
            return subprocess.CompletedProcess(argv, 0, "ok", "")
        if argv[3] == "transfer" and argv[5] == "1.000000":
            return subprocess.CompletedProcess(argv, 0, f"Signature: {SIG1}\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "blockhash expired")
    with pytest.raises(payout.PayoutError) as err:
        payout.execute(payout.plan(TARGET), wallet_dir=_wallet(tmp_path), payee="EK7H81j97oaupJijuzaK2WZvaLVKgJosbxyCiqWPupHs",
                       mint="4C6dtRowv5gGgdVxX3YdHmRwoD5vNt1W5wXGRcCvp3X1", runner=runner)
    assert err.value.partial["payout_tx"] == SIG1 and "fee_tx" not in err.value.partial
