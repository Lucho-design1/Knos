"""The revenue dashboard's data (web/revenue/): the fee config, what the chain holds, and a model that says it is one.

    python -m knos.money.revenue --out web/revenue_data.json [--offline] [--demo web/revenue_devnet.json]

Three parts, kept apart on the page and here:

  measured   read from devnet when the file was written (`read`): the treasury's fee accounts (test money), and the
             graduation demo's escrow and pool (web/revenue_devnet.json, SYNTHETIC claims). Knos's revenue is 0:
             every unit on devnet is test money. A part that was not read says null, never a guess.
  schedule   config/fees.yaml as knos.money.fees_config validated it, each line with its status.
  model      `model(inputs)`: revenue per line for volumes a reader types. Its inputs are all 0 by default, it is
             labelled a MODEL everywhere, and `one_billion` is arithmetic on the config's rates (what volume a rate
             needs to make 1B USD of fees), not a forecast.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from . import fees_config

MODEL_INPUTS = {        # volumes a month; every default is 0: a model with no inputs says 0
    "verifications": 0,          # hosted verifications (the month's free ones are taken first)
    "payout_volume_usd": 0,      # value released from escrow (bounties and orders included)
    "payouts": 0,                # how many releases (each pays at least the floor)
    "graduation_volume_usd": 0,  # escrow + pre-order value released after graduation
    "task_package_sales_usd": 0,
    "cloud_subscribers": {},     # {tier name: subscribers}
}
TARGET = Decimal(1_000_000_000)
MODEL_LABEL = ("MODEL: revenue for the volumes typed in, at the fee config's rates. Not a forecast; no volume here is measured. "
               "The payout line is a lower bound: the floor is charged per release, and the model knows only the month's total and count.")


def _d(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def model(inputs: dict | None = None, cfg: fees_config.FeeConfig | None = None) -> dict:
    """Revenue a month per line for `inputs` (MODEL_INPUTS' keys), in USD, two decimals. The payout floor applies per
    release, but the model knows only the month's volume and count, so its payout line, max(rate x volume, floor x
    releases), is a LOWER BOUND: the real fee is the sum over releases of max(rate x amount, floor), which is at least
    that. It also uses the standard rate: an order on an owner's Plan pays less."""
    cfg = cfg or fees_config.load()
    x = {**MODEL_INPUTS, **(inputs or {})}
    f = cfg.doc["fees"]
    lines: dict[str, Decimal] = {}
    free = _d(f["verification"]["free_per_month"])
    lines["verification"] = max(Decimal(0), _d(x["verifications"]) - free) * _d(f["verification"]["usd_each"])
    rate = Decimal(f["payout"]["rate_bps"]) / 10_000
    lines["payout"] = max(_d(x["payout_volume_usd"]) * rate, _d(x["payouts"]) * _d(f["payout"]["floor_usd"]))
    lines["graduation"] = _d(x["graduation_volume_usd"]) * Decimal(f["graduation"]["rate_bps"]) / 10_000
    lines["task_package"] = _d(x["task_package_sales_usd"]) * Decimal(f["task_package"]["knos_bps"]) / 10_000
    tiers = {t["name"]: _d(t["usd_month"]) for t in cfg.credit_tiers}
    subs = x.get("cloud_subscribers") or {}
    unknown = set(subs) - set(tiers)
    if unknown:
        raise ValueError(f"no Knos Cloud tier {sorted(unknown)}")
    lines["cloud"] = sum((tiers[n] * _d(c) for n, c in subs.items()), Decimal(0))
    cents = {k: str(v.quantize(Decimal("0.01"), ROUND_HALF_UP)) for k, v in lines.items()}
    total = sum(lines.values(), Decimal(0)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    status = {k: f[k]["status"] for k in ("verification", "payout", "graduation", "task_package")} | {"cloud": cfg.doc["cloud"]["status"]}
    return {"label": MODEL_LABEL, "inputs": x, "month": cents, "month_total": str(total), "year_total": str(total * 12), "status": status}


def one_billion(cfg: fees_config.FeeConfig | None = None) -> dict:
    """Arithmetic, not a forecast: the yearly volume each line alone would need for 1B USD of fees at the config's rates."""
    cfg = cfg or fees_config.load()
    f = cfg.doc["fees"]
    out = {"label": "DERIVED: 1,000,000,000 USD divided by each rate in config/fees.yaml. Arithmetic on the rates, not a forecast, not a plan.",
           "fees_usd": str(TARGET)}
    out["payout_volume_usd_year"] = str((TARGET * 10_000 / f["payout"]["rate_bps"]).quantize(Decimal(1)))
    out["verifications_year"] = str((TARGET / _d(f["verification"]["usd_each"])).quantize(Decimal(1)))
    if f["graduation"]["rate_bps"]:
        out["graduation_volume_usd_year"] = str((TARGET * 10_000 / f["graduation"]["rate_bps"]).quantize(Decimal(1)))
    if f["task_package"]["knos_bps"]:
        out["task_package_sales_usd_year"] = str((TARGET * 10_000 / f["task_package"]["knos_bps"]).quantize(Decimal(1)))
    top = max(cfg.credit_tiers, key=lambda t: _d(t["usd_month"]))
    out["cloud_subscribers_at_top_tier"] = str((TARGET / (_d(top["usd_month"]) * 12)).quantize(Decimal(1)))
    out["cloud_top_tier"] = top["name"]
    out["placeholders_used"] = [p for p in cfg.placeholders() if p.startswith(("fees.graduation", "fees.task_package", "cloud.tiers"))]
    return out


def treasury(ledger, cfg: fees_config.FeeConfig) -> dict:
    """The fee owner's token accounts for the counted mints and the faucet's test USDC, read now (test money)."""
    from ..settle.v2 import pay
    rows = []
    for label, mint in (("Circle devnet USDC (test)", pay.USDC_DEVNET), ("Knos faucet test USDC", pay.faucet_mint())):
        for i, acc in enumerate(pay.fee_accounts(mint)):
            bal = None
            if ledger is not None:
                data = ledger.account(acc)
                bal = int.from_bytes(bytes(data)[64:72], "little") if data is not None and len(data) >= 72 else 0
            rows.append({"mint": str(mint), "label": label, "i": i, "address": str(acc), "balance": bal})
    return {"fee_owner": cfg.doc["treasury"]["fee_owner"], "accounts": rows, "read": ledger is not None,
            "test_money_held": None if ledger is None else sum(r["balance"] or 0 for r in rows),
            "note": "test money on devnet: none of it is revenue"}


def demo(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    a = d.get("claims", {}).get("A", {}).get("state", {})
    return {"synthetic": True, "read": d.get("read"), "program": d.get("program"), "mint": d.get("mint"),
            "escrow_locked": a.get("escrow", {}).get("locked"), "pool_locked": a.get("pool", {}).get("locked"),
            "pool_buyers": a.get("pool", {}).get("buyers"), "signatures": d.get("signatures", []), "what": d.get("what")}


def build(ledger=None, demo_file: Path | None = None, cfg: fees_config.FeeConfig | None = None, now: datetime | None = None) -> dict:
    cfg = cfg or fees_config.load()
    return {"generated": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "revenue": {"usd": "0", "why": "Knos runs on Solana devnet only: every fee taken is test money. Nothing has been sold."},
            "schedule": cfg.public(), "treasury": treasury(ledger, cfg), "graduation_demo": demo(demo_file),
            "model": model({}, cfg), "one_billion": one_billion(cfg)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m knos.money.revenue")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--demo", type=Path, default=Path("web/revenue_devnet.json"))
    ap.add_argument("--offline", action="store_true", help="read no chain: the treasury's balances say null")
    a = ap.parse_args(argv)
    led = None
    if not a.offline:
        from .. import chain
        led = chain.ledger()
    a.out.write_text(json.dumps(build(led, a.demo), indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
