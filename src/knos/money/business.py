"""Knos's prices in numbers: who pays, and how much. Writes JSON; nothing that shows it types a number of its own.

    python -m knos.money.business --out <file> [--team-data <dashboard file>]

Two kinds of number, never mixed, each labelled where it is shown:

  price     config/fees.yaml through knos.money.fees_config (starting prices, nobody pays yet)
  model     price x volume for volumes a reader types (all 0 by default). MODEL, NOT A FORECAST.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import fees_config

LABEL = ("MODEL, not a forecast: price x volume at config/fees.yaml's starting prices. No volume here is measured, nobody "
         "pays any of these prices yet (devnet: revenue 0), and revenue is not free cash flow (cost per verification not measured).")
INPUTS = {"verified_merges": 0, "agent_checks": 0, "bounty_volume_usd": 0, "task_packages": 0, "task_package_price_usd": 0}

def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _q(d: Decimal, places: str = "0.01") -> str:
    return str(d.quantize(Decimal(places), ROUND_HALF_UP))


def prices(cfg: fees_config.FeeConfig) -> list[dict]:
    """The four lines a customer meets, each from the fee config with its status."""
    f = cfg.doc["fees"]
    vm, x, b, tp = f["verified_merge"], f["x402_check"], f["bounty_platform"], f["task_package"]
    return [
        {"who": "a team running coding agents", "line": "verified merge", "price": f"{vm['usd_each']} USD per verified merge",
         "free": f"first {vm['free_first']} verification free", "status": vm["status"], "label": vm.get("label", ""),
         "paid_with": "USDC on Solana: x402 exact or a knos_pay order (held until the proof passes)", "source": vm["source"]},
        {"who": "an agent paying for itself", "line": "raw agent check over x402", "price": f"{x['usd_each']} USD per check",
         "free": "", "status": x["status"], "label": "starting price", "paid_with": "x402 v2 exact on Solana (x402.org facilitator), per call", "source": x["source"]},
        {"who": "a team posting a bounty", "line": "bounty fee", "price": f"{b['rate_bps'] / 100:g}% of the bounty",
         "free": "", "status": b["status"], "label": "starting price", "paid_with": "0.30% (at least 0.05) taken by knos_pay at payout, the rest invoiced",
         "source": b["source"]},
        {"who": "an AI lab buying verified tasks", "line": "verified task package", "price": f"maintainer {100 - tp['knos_bps'] / 100:g}% / Knos {tp['knos_bps'] / 100:g}%",
         "free": "", "status": tp["status"], "label": "starting split", "paid_with": "by contract (not a knos_pay order today)", "source": tp["source"]},
    ]


def model(inputs: dict | None = None, cfg: fees_config.FeeConfig | None = None) -> dict:
    """Revenue a month for the volumes typed in. The bounty line is the WHOLE 5% (its on-chain 0.30% included)."""
    cfg = cfg or fees_config.load()
    f = cfg.doc["fees"]
    x = {**INPUTS, **(inputs or {})}
    lines = {"verified_merge": _d(x["verified_merges"]) * _d(f["verified_merge"]["usd_each"]),
             "agent_checks": _d(x["agent_checks"]) * _d(f["x402_check"]["usd_each"]),
             "bounty_fee": _d(x["bounty_volume_usd"]) * Decimal(f["bounty_platform"]["rate_bps"]) / 10_000,
             "task_packages": _d(x["task_packages"]) * _d(x["task_package_price_usd"]) * Decimal(f["task_package"]["knos_bps"]) / 10_000}
    total = sum(lines.values(), Decimal(0))
    return {"label": LABEL, "inputs": x, "month": {k: _q(v) for k, v in lines.items()}, "month_total": _q(total), "year_total": _q(total * 12)}


def build(cfg: fees_config.FeeConfig | None = None, team: dict | None = None) -> dict:
    cfg = cfg or fees_config.load()
    return {"revenue_today_usd": "0", "why": "devnet only: every payment is test money; nothing has been sold",
            "prices": prices(cfg), "model": model({}, cfg),
            "rails": {"today": "USDC on Solana devnet: x402 v2 exact via the public x402.org facilitator (no key), or held by knos_pay until the proof passes"},
            "onboarding": ["uv tool install knos   (or pipx install knos)",
                           "knos verify --agent \"<your agent>\"   in a checkout with the agent's change committed (first verification free)",
                           "then every agent PR: the GitHub Action (action.yml) on the repository, or the knos_verify tool of `knos mcp` inside the agent"],
            "team": team}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m knos.money.business")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--team-data", type=Path, default=None, help="a dashboard JSON (python -m knos.money.teams dashboard) to show")
    a = ap.parse_args(argv)
    team = json.loads(a.team_data.read_text(encoding="utf-8")) if a.team_data and a.team_data.is_file() else None
    a.out.write_text(json.dumps(build(team=team), indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
