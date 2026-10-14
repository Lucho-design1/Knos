"""Knos's business in numbers: who pays, how much, and the arithmetic of the path to 1B USD a year. The pricing page
(web/teams/) and the stats page read the JSON this writes; nothing on them types a number of its own.

    python -m knos.money.business --out web/teams_data.json [--team-data web/team_data.json]

Three kinds of number, never mixed, each labelled where it is shown:

  price     config/fees.yaml through knos.money.fees_config (decided 14 Oct 2026: starting prices, nobody pays yet)
  sourced   an outside or audited figure with its page and the day it was read (fees.yaml `sources`)
  model     price x volume for volumes a reader types (all 0 by default) and the 1B USD arithmetic: what volume each
            line ALONE needs, and what a share of GitHub's merges would give. MODEL, NOT A FORECAST. Revenue, not cash
            flow: Knos's cost per verification is not measured yet, so no margin or free cash flow is stated.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import fees_config

TARGET = Decimal(1_000_000_000)
LABEL = ("MODEL, not a forecast: price x volume at config/fees.yaml's starting prices. No volume here is measured, nobody "
         "pays any of these prices yet (devnet: revenue 0), and revenue is not free cash flow (cost per verification not measured).")
INPUTS = {"verified_merges": 0, "agent_checks": 0, "bounty_volume_usd": 0, "task_packages": 0, "task_package_price_usd": 0}

# sourced figures (fees.yaml `sources` holds the same with its page and the day it was read)
GITHUB_MERGED_PRS_MONTH = 90_000_000           # "more than 90 million" a month: GitHub, via Visual Studio Magazine, 30 Jun 2026
EPOCH_TASK_USD = (200, 2_000)                  # "$200 to $2000 mostly" per task: Epoch AI, 12 Jan 2026
SLOP = {"claimed_pass_with_finished_ci": 3_736, "of_which_failing": 1_119, "failing_measured_check": 8_954, "of_which_merged": 6_059,
        "agent_prs_with_files": 69_654}


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
         "paid_with": "USDC on Solana: x402 exact or a knos_pay escrow", "source": vm["source"]},
        {"who": "an agent paying for itself", "line": "raw agent check over x402", "price": f"{x['usd_each']} USD per check",
         "free": "", "status": x["status"], "label": "starting price", "paid_with": "x402 v2 exact on Solana (x402.org facilitator), per call", "source": x["source"]},
        {"who": "a team posting a bounty", "line": "bounty fee", "price": f"{b['rate_bps'] / 100:g}% of the bounty",
         "free": "", "status": b["status"], "label": "starting price", "paid_with": f"0.30% (at least 0.05) taken by knos_pay at payout, the rest invoiced",
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


def billion(cfg: fees_config.FeeConfig | None = None) -> dict:
    """The 1B USD a year path as arithmetic on the starting prices and the sourced figures."""
    cfg = cfg or fees_config.load()
    f = cfg.doc["fees"]
    vm = _d(f["verified_merge"]["usd_each"])
    per_month = TARGET / 12
    knos_share = Decimal(f["task_package"]["knos_bps"]) / 10_000
    alone = {
        "verified_merges_a_month": _q(per_month / vm, "1"),
        "verified_merges_share_of_github_merges": _q(per_month / vm / GITHUB_MERGED_PRS_MONTH * 100, "0.1") + "%",
        "agent_checks_a_month": _q(per_month / _d(f["x402_check"]["usd_each"]), "1"),
        "bounty_volume_usd_a_year": _q(TARGET * 10_000 / f["bounty_platform"]["rate_bps"], "1"),
        "task_packages_a_year_at_200_usd": _q(TARGET / (Decimal(EPOCH_TASK_USD[0]) * knos_share), "1"),
        "task_packages_a_year_at_2000_usd": _q(TARGET / (Decimal(EPOCH_TASK_USD[1]) * knos_share), "1"),
    }
    shares = [1, 5, 10, 25, 50]
    github = [{"share_pct": s, "verified_merges_a_month": int(GITHUB_MERGED_PRS_MONTH * s / 100),
               "usd_a_year": _q(Decimal(GITHUB_MERGED_PRS_MONTH) * s / 100 * vm * 12, "1")} for s in shares]
    return {"label": "ARITHMETIC on the starting prices and the sourced figures; not a forecast, not a plan.",
            "target_usd_a_year": str(TARGET), "each_line_alone": alone, "share_of_github_merges_at_starting_price": github,
            "inputs": {"github_merged_prs_a_month": GITHUB_MERGED_PRS_MONTH, "verified_merge_usd": str(vm),
                       "agent_check_usd": f["x402_check"]["usd_each"], "bounty_fee_bps": f["bounty_platform"]["rate_bps"],
                       "task_package_knos_bps": f["task_package"]["knos_bps"], "lab_task_usd": list(EPOCH_TASK_USD)},
            "reading": ("At 1.00 USD, verified merges ALONE reach 1B USD a year only at about 83 million a month: more than 90% of "
                        "every pull request GitHub merges today. So the path is several lines together (merges, agent checks, "
                        "bounty escrow, lab task packages) and a price that follows the measured cost and value, not one line.")}


def why_now() -> dict:
    s = SLOP
    return {"claim_vs_ci": f"{s['of_which_failing']:,} of {s['claimed_pass_with_finished_ci']:,} agent pull requests that said tests pass had a failing check "
                           f"({s['of_which_failing'] / s['claimed_pass_with_finished_ci']:.0%})",
            "merged_anyway": f"{s['of_which_merged']:,} of {s['failing_measured_check']:,} agent pull requests that fail a measured Knos check were merged anyway "
                             f"({s['of_which_merged'] / s['failing_measured_check']:.0%})",
            "per_1000": f"about {round(s['of_which_merged'] * 1000 / s['agent_prs_with_files'])} failing merges per 1,000 agent pull requests in the audit",
            "source": "docs/reference/SLOP_AUDIT.md (Knos's own audit of the hao-li/AIDev dataset, GitHub check records read 13 Oct 2026)",
            "volume": f"GitHub merges more than {GITHUB_MERGED_PRS_MONTH // 1_000_000} million pull requests a month",
            "volume_source": "GitHub, via Visual Studio Magazine, 30 Jun 2026 (read 14 Oct 2026)",
            "labs": f"labs pay {EPOCH_TASK_USD[0]:,} to {EPOCH_TASK_USD[1]:,} USD per task (mostly) and consistently cite robustness against reward hacking as a quality criterion",
            "labs_source": "Epoch AI, 12 Jan 2026 (read 14 Oct 2026)"}


def build(cfg: fees_config.FeeConfig | None = None, team: dict | None = None) -> dict:
    cfg = cfg or fees_config.load()
    return {"revenue_today_usd": "0", "why": "devnet only: every payment is test money; nothing has been sold",
            "prices": prices(cfg), "model": model({}, cfg), "scale": billion(cfg), "why_now": why_now(),
            "sources": {k: v for k, v in cfg.doc["sources"].items() if k in ("github_merges", "epoch_tasks", "slop_audit")},
            "rails": {"today": "USDC on Solana devnet: x402 v2 exact via the public x402.org facilitator (no key), escrow via knos_pay",
                      "later": "card and bank through Airwallex (not built; no account yet). No Stripe."},
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
