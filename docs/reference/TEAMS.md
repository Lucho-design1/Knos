<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Knos for teams: prices, paying, metering, invoices, the dashboard

**In plain words.** A team that runs coding agents posts work, its agents do it, and Knos's referee decides on sealed
tests whether the work counts. The team pays for each pull request the referee verified; an agent can pay for a single
check itself; a bounty is held and paid on the verdict.

Everything is counted per team and per agent, and the
invoice bills only what the chain confirms. Devnet only today: every payment is test money, and Knos's revenue is 0.

Code: `src/knos/money/teams.py` (metering, invoices, dashboard), `src/knos/money/business.py` (prices),
`src/knos/nebius/flow.py` (the one flow end to end). Tests: `tests/test_money_teams.py`, `tests/test_nebius_flow.py`.

## Who pays, and how much

Starting prices decided on 14 Oct 2026, from [config/fees.yaml](../../config/fees.yaml) (the one fee
config). Nobody pays them yet.

| who pays | for | price | status |
|---|---|---|---|
| a team running coding agents | a **verified merge**: a pull request the referee verified (sealed tests passed, no cheat rule fired, the re-run agreed) | **1.00 USD**, the team's first verification free | decided, starting price |
| an agent paying for itself | a **raw check** over x402 | **0.02 USD** per check | decided |
| a team posting a bounty | the **bounty fee** | **5%** of the bounty; `knos_pay` takes its 0.30% (at least 0.05) at payout, the rest is invoiced | decided (on-chain part live) |
| an AI lab | a **verified task package** (issue + hidden tests + cheat rules) | maintainer **90%** / Knos **10%** | decided |

## Paying, end to end, without Stripe

- **USDC on Solana.** A raw check is paid with x402 v2 `exact` through the public x402.org facilitator (no key; the
  facilitator pays the network fee): `knos.money.x402_exact`, used by the flow (`knos.nebius.onchain.Devnet.pay_check`).
  A bounty is held by `knos_pay` (`fund_wallet_ix`) and released on the verdict.
- **Card and bank:** through Airwallex later (not built; no account yet). No Stripe.

## The one flow, and its devnet evidence

`python -m knos.nebius flow --out DIR [--wallets DIR]` ([examples/nebius/README.md](../../examples/nebius/README.md)):
post (seal + money held) -> Nemotron 3 Super writes, runs and tests code -> the agent pays one check over x402 -> Tavily
provenance -> the Knos referee -> paid -> metered and invoiced.

Two runs on 14 Oct 2026, one team record (`examples/nebius/flow-run/usage.jsonl`, labelled internal dogfooding; the
model replies were MOCK because no Token Factory key was set; the test runs, the referee and the chain were real). Own
devnet wallets (team `hZ6VVnyNd1eqBFt7WDZXHtBF4coTsJjjp6rT1sYTNQz`, agent `3sCqCbXSHqEonAKtkHK5Lt6N3216VENpy9G8MEmXvDdf`),
own test mint `7mHYTL1fmdiaHcYDLVJVz9zqgFdssqFNQAjVZYYQnR1p` (synthetic test units):

| step | run 1 | run 2 |
|---|---|---|
| money held, 5.00 test units (devnet, finalized) | `3ofNVFEyHoodeWAwFW46oygXSaVv7GxRHvsGjTooKiKdvMSbt9twaeEHoiBbXVL4XRo3fZfiKhyjZGGDba4iT9mh` (1,861 ms) | `2dWrwKMfHURPXSLxUgo6UkaCNPGC6t7sik4BgcRNRQZknFMNiyDkU6j1RdYRjy7TTiLy379geZUSHEzXz4nGQdEa` (1,557 ms) |
| agent's check over x402, 0.02 (devnet, finalized) | `5KtTdsE32va9X1QYwzAVgZEdkiYcQprvXxmTVsSTE14VcJ1RgUsMhV52Yxtt7mAxnzwfdYekeaywjw3ELAGhE6p1` (2,897 ms) | `3YXhV5wTRFz6E4q4XxxyqeGgH7zQh1zaEuGSJZDDPUjvbeBGoVrAJkaAsYAa99Hk6gmJudbr1ncFRqapUWWihkw9` (2,674 ms) |
| referee on the agent's code | accepted, re-run agreed | accepted, re-run agreed |
| referee on the scripted cheater (synthetic) | refused: `test_edited` (its own tests passed) | refused: `test_edited` |
| payout 4.95 to the agent + 0.05 fee (**LiteSVM, not devnet**) | `tzsH8pBbZfdBMdKt7G7T8Fq8kY9g1b2hVvD5DYEb5kMe9kEMtw1RpCDAqn66ombCMmi1XKEanm4WvtdkfwEdxTy` | `3EBr9suymbL5dG3kYWu17Vy56oUSZP3pB1xAH4RV2FUftXL59NgiuDgwhKsxE88XPaA6R3HhjfBdpEpficSVdeeu` |
| invoice | 0.00 (first verification free) | 1.00 (one verified merge) |

"Paid and final": send -> finalized of those four devnet transactions, measured by polling `getSignatureStatuses`:
p50 2,267 ms, p95 2,897 ms (n = 4, Knos's own test traffic over the public devnet RPC; the time includes the RPC round
trips). Devnet answered `getAgGenesisCert` with a certificate (Alpenglow), and each transaction was `confirmed` and
`finalized` at the same status read.

Why the payout is LiteSVM: `knos_pay` releases a job only on a GitHub Actions OIDC token from a signed run of the
prove.yml the job pins. A task judged outside GitHub has no such run, so no `knos` command can release it on a
verdict.

The flow replays the same job (amount, terms, pin) with the test builds and pays it there; the devnet held money can go
back to the team after their deadline (1 day): anyone may send the refund (`refund_ix`), as the relay's upkeep does.
This gap (no release on a verdict without GitHub Actions) is logged as a pain to fix.

In the example the hidden tests sit in the repository (`examples/nebius/task/hidden/`) so anyone can re-run it; the
agent's prompt never includes them. A real team keeps them outside the repository (a private repository or a secret).

## Metering, invoices, the dashboard

```bash
python -m knos.money.teams usage     --file usage.jsonl                      # per team, per agent
python -m knos.money.teams invoice   --file usage.jsonl --team T --chain     # each transaction checked on devnet
python -m knos.money.teams dashboard --file usage.jsonl --team T --chain --out web/team_data.json
python -m knos.money.business --out web/teams_data.json --team-data web/team_data.json
```

- **Usage record:** append-only JSONL, one event a line: `verification` (passed, cheat rules, whether the agent said its
  tests pass), `x402_check`, `escrow_funded`, `payout`, each with its transaction and network when it has one.
- **Invoice:** the team's first verification is free (`free_first` in fees.yaml), then 1.00 USD per verified merge; a
  refused change costs nothing; an x402 check was paid at the call and is never billed again; the bounty fee's
  off-chain part is billed at payout. A line whose transaction the chain does not show as finalized (or that failed,
  or that ran in LiteSVM) is shown and not billed.
- **Dashboard:** verifications, verified, refused, cheats caught, **failing merges blocked** (the agent said its tests
  pass and the referee refused: each is a failing merge that did not happen; no dollar value is put on it, because
  none is sourced), paid checks, and "paid and final in N ms" from devnet transactions only.

## Start in under five minutes

1. `uv tool install knos` (or `pipx install knos`).
2. In a checkout with the agent's change committed: `knos verify --agent "<your agent>"`. The first verification is free.
3. For every agent pull request: the GitHub Action (`action.yml`) on the repository, or the `knos_verify` tool of
   `knos mcp` inside the agent.

## Limits

- Devnet only; every amount is test money; revenue 0. No customer pays any of these prices.
- The payout leg ran in LiteSVM (above). The 1.00 USD invoice was computed, not paid on chain.
- The scripted cheater is synthetic; the referee's decisions on it are real.
- Card and bank (Airwallex) are not built.
