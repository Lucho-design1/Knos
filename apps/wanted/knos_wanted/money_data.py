"""The money page: what Knos charges, as config/fees.yaml says (knos.money.fees_config), read once when the app starts.
Served at GET /api/money; the page adds what is held, released and charged, summed from GET /api/projects."""
from __future__ import annotations


def _prices() -> list[dict]:
    """The price list, one row a line: what, the price, who pays, and whether it is charged today."""
    try:
        from knos.money import fees_config
        f = fees_config.load().doc["fees"]
    except Exception:  # noqa: BLE001 - no knos package or no config here: the page says the list is not readable
        return []
    pay = f["payout"]
    live = f"{pay['rate_bps'] / 100:g}% (at least {pay['floor_usd']} test units) on each release, in test money on devnet"
    return [
        {"what": "Demand check", "price": f"{f['demand_check']['free_a_month']} a month free", "payer": "nobody", "today": "free"},
        {"what": "Deep demand check", "price": f"{f['deep_demand_check']['usd_each']} USD each, by card once the company exists",
         "payer": "the company", "today": "nobody is charged: no company is formed yet"},
        {"what": "Ready brief", "price": "free", "payer": "nobody", "today": "free"},
        {"what": "Proof page", "price": "free", "payer": "nobody", "today": "free"},
        {"what": "Release on verified proof", "price": f"{f['release']['rate_bps'] / 100:g}% on top, plus payment costs; the solver keeps 100%",
         "payer": "the company", "today": f"devnet charges {live} until the timelocked upgrade"},
        {"what": "How a milestone is paid", "price": "by card up to 500 USD; larger milestones by bank transfer or in real money (Circle's USDC)",
         "payer": "the company", "today": "devnet test units only"},
    ]


MONEY = {
    "checked": "2026-10-23",
    "pools": [],             # read by the server's money_doc; the page no longer draws it
    "prices": _prices(),
}
