"""Pay the improvers: each accepted improvement (canary) pays its target's bounty on devnet, with the fee from THE one
fee config (config/fees.yaml through knos.money.fees_config, line `bounty`: the funder pays amount + fee, the payee
receives the amount, the fee goes to the treasury).

On devnet the loop's treasury is a wallet of the loop's own (a stand-in for Knos's Squads vault, which nothing in Knos
signs for). The payee is the agent owner's devnet wallet. The fee goes to the token account of the real treasury owner
(knos_pay FEE_OWNER, the Squads vault PDA) for the loop's test mint, as knos_pay itself pays fees. Test tokens only:
worth nothing, revenue stays 0. Mainnet is refused.

    plan(target)                          amounts, from the fee config
    execute(plan, wallet_dir=, payee=, mint=)   two SPL transfers with the spl-token CLI; returns their signatures
"""

from __future__ import annotations

import re
import subprocess
from decimal import Decimal
from pathlib import Path

ALLOWED_RPC = ("https://api.devnet.solana.com", "http://127.0.0.1:8899", "http://localhost:8899")
SIG = re.compile(r"Signature:\s*([1-9A-HJ-NP-Za-km-z]{80,90})")


class PayoutError(RuntimeError):
    pass


def plan(target: dict, fees=None) -> dict:
    from ..money import fees_config
    cfg = fees if fees is not None else fees_config.load()
    amount = fees_config.micro(str(target["bounty_usd"]), "bounty_usd")
    got = cfg.bounty(amount)
    return {"amount": got["amount"], "fee": got["fee"], "total": got["total"], "fee_to": "treasury",
            "treasury_owner": got["treasury"], "fee_line": "fees.bounty", "fee_config": "config/fees.yaml",
            "status": got["status"], "target": target["id"]}


def ui(micro: int, decimals: int = 6) -> str:
    return str((Decimal(micro) / (10 ** decimals)).quantize(Decimal(1).scaleb(-decimals)))


def rpc_of(cfg: Path) -> str:
    """The json_rpc_url line of a Solana CLI config, exactly (not a substring of the file)."""
    for line in cfg.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "json_rpc_url":
            return value.strip().strip('"').strip("'")
    return ""


def _spl(args: list[str], cfg: Path, runner) -> str:
    done = runner(["spl-token", "--config", str(cfg), *args], capture_output=True, text=True, timeout=180)
    if done.returncode != 0:
        raise PayoutError(f"spl-token {args[0]}: {(done.stderr or done.stdout).strip()[-300:]}")
    return done.stdout


def _pubkey(path: Path, runner) -> str:
    done = runner(["solana-keygen", "pubkey", str(path)], capture_output=True, text=True, timeout=30)
    if done.returncode != 0:
        raise PayoutError(f"solana-keygen pubkey: {done.stderr.strip()[-200:]}")
    return done.stdout.strip()


def fee_account(mint: str, owner: str) -> str:
    """The associated token account of `owner` (the treasury PDA, off the curve) for `mint`."""
    from solders.pubkey import Pubkey
    token = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
    ata = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
    got, _ = Pubkey.find_program_address([bytes(Pubkey.from_string(owner)), bytes(token), bytes(Pubkey.from_string(mint))], ata)
    return str(got)


def execute(p: dict, *, wallet_dir, payee: str, mint: str, rpc: str = "https://api.devnet.solana.com",
            runner=subprocess.run) -> dict:
    """Two transfers from the loop's devnet treasury wallet (<wallet_dir>/treasury.json, config <wallet_dir>/cli.yml):
    the amount to the payee, the fee to the treasury owner's token account. Every key and fee payer is named on the
    command line: the machine's default Solana keypair is never used."""
    if rpc not in ALLOWED_RPC:
        raise PayoutError(f"{rpc}: the loop pays on devnet or a local validator only")
    wd = Path(wallet_dir).expanduser()
    cfg, key = wd / "cli.yml", wd / "treasury.json"
    if not cfg.is_file() or not key.is_file():
        raise PayoutError(f"no loop treasury wallet in {wd} (cli.yml, treasury.json)")
    if rpc_of(cfg) != rpc:
        raise PayoutError(f"{cfg} does not point at {rpc}")
    payer = _pubkey(key, runner)
    common = ["--owner", str(key), "--fee-payer", str(key)]
    out = _spl(["transfer", mint, ui(p["amount"]), payee, *common, "--fund-recipient", "--allow-unfunded-recipient"], cfg, runner)
    m = SIG.search(out)
    if not m:
        raise PayoutError("the payout transfer printed no signature")
    result = {"payout_tx": m.group(1), "payer": payer, "payee": payee, "mint": mint, "cluster": "devnet",
              "amount": p["amount"], "fee": p["fee"]}
    if p["fee"] > 0:
        try:
            _fee(p, result, mint, cfg, key, runner)
        except PayoutError as why:       # the amount went out and the fee did not: say exactly what was sent
            why.partial = result
            raise
    return result


def _fee(p: dict, result: dict, mint: str, cfg: Path, key: Path, runner) -> None:
    fee_to = fee_account(mint, p["treasury_owner"])
    have = runner(["spl-token", "--config", str(cfg), "account-info", "--address", fee_to], capture_output=True, text=True, timeout=60)
    if have.returncode != 0:
        made = _spl(["create-account", mint, "--owner", p["treasury_owner"], "--fee-payer", str(key)], cfg, runner)
        m2 = SIG.search(made)
        result["fee_account_tx"] = m2.group(1) if m2 else ""
    out = _spl(["transfer", mint, ui(p["fee"]), fee_to, "--owner", str(key), "--fee-payer", str(key)], cfg, runner)
    m3 = SIG.search(out)
    if not m3:
        raise PayoutError("the fee transfer printed no signature")
    result.update({"fee_tx": m3.group(1), "fee_account": fee_to})
