<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Money: one fee config, graduation, splits, x402 and the revenue page

**In plain words.** Every Knos fee lives in one file, and the code reads it from there. When a claim passes, money for its next step and its first orders waits in escrow on devnet. When the work is accepted, everyone who helped is paid their share at once.

How the money moves:

1. A verdict passes (works, wanted, makeable).
2. It opens a milestone escrow and a pre-order pool: knos_pay orders.
3. The judge workflow signs acceptance: the split is paid to the researcher, agent, lab and referee, and the fee goes to the treasury.
4. If the deadline passes first, the money and the fee go back to whoever paid.

**Revenue today: 0.** Knos runs on Solana devnet only. Every fee the program takes there is test money, and nothing
has been sold. Every price below says whether it is **live** (the deployed program charges it on devnet), **proposed**
(the price book, nobody pays it yet) or a **placeholder** (a number only the founder can set).

## The one fee config: `config/fees.yaml`

Code reads it only through `knos.money.fees_config`:

```python
from knos.money import fees_config
cfg = fees_config.load()                 # validated; KNOS_FEES names another file
cfg.fee("bounty", 20_000_000)            # 60_000: base units of a 6-decimal mint, exactly knos_pay's order fee
cfg.bounty(20_000_000)                   # amount, fee, total the funder pays, fee_to "treasury"
cfg.price("verification", 10, used=0)    # count-based lines take the month's free uses first
cfg.split(100_000_003)                   # the contributor split, rounded as the program rounds
cfg.task_package(2_000_000_000)          # Knos's share and the maintainer's
cfg.placeholders()                       # every number the founder has not set
```

The live lines repeat numbers compiled into `knos_pay` (`knos.settle.v2.pay`) and the proposed lines repeat the price
book (`knos.billing`). The loader **refuses** the file when one of them differs, so the file, the program and the price
book cannot drift apart: changing a live fee means upgrading the program through the multisig.

| line | rate or price | status | who pays, and where it goes |
|---|---|---|---|
| verification | 0.002 USD each after 100,000 a month; public repositories and self-hosting free | proposed | the buyer of hosted checks |
| payout | 0.30% of the amount, at least 0.05 | live | the funder, on top; the program sends it to the treasury at release |
| bounty | 0.30%, at least 0.05 (a bounty is a work order) | live | the funder, on top; to the treasury; returned on a refund |
| funding | 0 at funding: the program holds the payout fee and takes it only at release | live | nobody, until a release |
| graduation | 0.50% of the value released after graduation | placeholder | by contract, off chain, until a knos_pay build carries it |
| task package | 10% to Knos, the rest to the maintainer | placeholder | the lab that buys the package |
| x402 check | 0.002 USD each, sold in packs | proposed | the agent that calls `/checks` |

**The treasury** is the program's fee owner, `4G3cznCnwCUPBCZwzKiLupjdgB5pSoCcGWNGuFv4TYFo`, a vault of the Squads
program. Fees land in token accounts it owns (`pay.fee_accounts(mint)`: the associated account and any seeded
shards). Only a Squads proposal of the vault moves them; nothing in Knos signs for it. Out of each fee the relayer who
sends the payment keeps its tip (0.05, or 0.30 on a payee's first payment); the rest is the fee owner's
(`knos.billing.release_split`).

## Contributor splits

Every payout is shared among four roles, by fixed basis points (`splits.roles`, placeholders):

| role | basis points |
|---|---|
| researcher | 6000 |
| agent | 2500 |
| lab | 1000 |
| referee | 500 |

One knos_pay order pays one to four payees, so the split is the payee list of the judge's pay token
(`knos.splits.payees`). The program divides the amount: each share rounded down, the last payee the rest. A role that
took no part leaves its share to the others in proportion. Nobody forwards money after the fact: the split is paid in
the one transaction that pays the order.

## Graduation: the milestone escrow and the pre-order pool

`knos.graduation.plan(verdict, claim_id=, repo_id=, amount=, contributors=)` refuses any verdict that did not pass all
three checks of the referee. For one that did, it plans two kinds of knos_pay work order:

- **the milestone escrow**: a funder locks `amount` for the next milestone (the payout fee on top). The research
  repository's pinned `prove.yml` run, signed by GitHub and verified on chain, pays it to the split. After the
  deadline anyone can send RefundOrder and the funder gets the amount and the fee back.
- **the pre-order pool**: each buyer funds one order in the claim's pool scope. `graduation.pool(ledger, plan)` reads
  the pool from the chain (distinct buyers, amount locked in open orders still in time, and whether the bar of N buyers
  and X locked is met). It counts only the plan's own orders, in the mint the makers accept: the scope is public, so an
  order funded there with a worthless mint, other terms, another judge or other pinned workflows is listed as ignored; `graduation.demand_orders` hands it to the referee's demand book.

Both are **private** orders (`F_PRIVATE`, salted scope): they store no repository and no issue, so a claim never shows
up as a bounty on a GitHub issue. The salt is `sha256("knos-grad:" + claim id)`, derived from the public claim id on
purpose, so anyone can find a claim's escrow and pool. No token here pays backers out of revenue: a pre-order buys the
product, and an escrow funds a milestone or comes back.

### On devnet (13 Oct 2026)

`python -m knos.graduation.devnet` ran on the public knos_pay program with SYNTHETIC claims and a test mint of its own
(`CP6GfXRQeVhdgQHpLZ3Bb4CQwopFsdb3XSuwwdagoPJa`, 6 decimals, no freeze authority), from the wallet
`2x1YKK5uHktXLkg5aq6Z5nRV95AYg62dwLNp5YEAYBHu`. Every signature is in `web/revenue_devnet.json`:

| step | signature |
|---|---|
| claim A: milestone escrow, 50 test units | `2G9C94R5rw66HxwRPRoenHMpuZPxHtu32w6fk2UixWdroBW4kBULaMEZVzk2i985pbbqEy7CuQknMpAw3WA2LrFP` |
| claim A: pre-order, 20 test units | `3A7NNa5M5wAHUSbwiHmdxYM7bySvxG3ykdSijCsYwsE4pQcwGtq5hsvmNtMgdCzKUqXrLGkWAxdmA8AottBQkJXu` |
| claim A: pre-order, 10 test units | `5yfwjKJSupwc93TsCyrXSZ8deax5PYn3u8oCCRntPKGXKqSJRHja8gp75dRgU1AifvS3LDEh5r6Htv8s5cFP5ka6` |
| claim B: pre-order with a 60 s deadline | `wf7AxxrXXAJT26BbX8WJwzNYZBn1ogxs6AtdVRRZ2eXYFEYrcpHYs3docaLw45TsGSK2bojxM578WLc9gnf8YwW` |
| claim B: refunded by another relayer, amount and fee | `4hoBffMGkCzDKWfNdr95VJd9odDF26RV3fps994B9tmtGRxEncQaqujXQuKmdqW7dkbc8MNtvfjMk6DdJ54RAwcs` |
| claim B again: pre-order | `62xKk3w85zrFNawRK97JTy7MMgSUnjCn8pjjUaTagnWxqNbdGj3A8VK2BNEYaRY7dPF1fQ1rVyihBNY4w89Pq4cJ` |
| claim B again: refunded by the demo | `2iHXMseNnNXhD3zcp9tKAtqqFv7wDzFdUsF6Fm7ZCZ3vKchvQFiYAdLRnjFffF5nqH2DmuH3cu2zictJkMv4ueNZ` |

The first refund of claim B was sent by a relayer the demo does not run, before the demo's own: anyone may refund an
order past its deadline. The payout of claim A needs a GitHub-signed token from the judge repository; the demo does
not fake one. The payout path, with the four-way split and the fee, runs against the program's test build in LiteSVM
(`tests/test_money_graduation.py`), and the audience the judge would sign is in `web/revenue_devnet.json`.

## For agents: MCP, Hermes and x402

`knos.money.agent` has three tools in the MCP shape: `knos_fees`, `knos_graduate` and `knos_preorder`. They quote and
plan, and return the unsigned instruction the paying wallet signs itself; they never read a key. `agent.call(name,
args)` answers one, for an MCP server or a Hermes plugin (`ctx.register_tool`).

`python -m knos.money.x402 --plans web/revenue_devnet.json --mint <mint>` runs the x402 endpoint (anyone runs it;
Knos hosts none), on the proposed `knos-order` scheme of [X402.md](X402.md):

- `GET /fees` and `GET /pool/<claim>`: free.
- `GET /preorder/<claim>`: `402` with a requirement to fund a pre-order in the pool; asked again with
  `PAYMENT-SIGNATURE` naming the order, `200` "escrowed" once the chain shows it in that pool.
- `GET /checks`: `402` for a pack of paid checks (the smallest order is 5.00); each call is signed by the funding
  wallet over `knos-check:<order>:<n>`, and a replay or a stranger's call is refused. The count of each order is kept
  in a state file (`--state`), written before the call is answered, so a restart does not sell a call again.

## The revenue page: `web/revenue/`

`python -m knos.money.revenue --out web/revenue_data.json` writes what the page draws, in three parts kept apart:

- **measured**: the treasury's fee accounts and the demo's escrow and pool, read from devnet when the file was
  written. All of it is test money. A part that was not read says so; it is never guessed.
- **schedule**: this config, each line with its status.
- **model**: revenue for volumes the reader types, at the config's rates. It is labelled a MODEL, its inputs start at
  0, and a model with no inputs says 0. Its payout line is a lower bound: the floor is charged on each release, and the
  model sees only the month's total and count. Its "1B USD question" is arithmetic on the rates (for example, 0.30% of
  333,333,333,333 USD released in a year), not a forecast.

## Knos Cloud credits (placeholders)

Everything stays open source (MIT) and self-hosting stays free. Knos Cloud would sell credits for hosted verification:
runners, sealed-test storage, receipts, and Gate for private repositories. The tiers are placeholders:

| tier | USD a month | credits a month |
|---|---|---|
| Starter | 20 | 10000 |
| Pro | 100 | 55000 |
| Team | 200 | 120000 |

The shape is copied from Nous Research, which sells open-core software (MIT) with hosted subscriptions on credits
(Portal tiers of $20, $100 and $200) and enterprise deals; it reported about $36M annualized revenue by mid-September
2026 and raised $90M at a $1.5B valuation (TechCrunch, 7 Oct 2026, citing the Wall Street Journal; unaudited). Knos
copies the shape, not the numbers. Labs pay 200 to 2,000 USD per verified task (Epoch AI, 12 Jan 2026), which is
where a task package would sell.

## Decisions only the founder can make

- Every placeholder: the graduation rate, Knos's share of a task package, the split's basis points, the credit price
  and the three tiers (`cfg.placeholders()` lists them).
- Whether a graduation fee is charged off chain by contract or added to a knos_pay build (an upgrade through the
  multisig).
- Any token that pays backers out of revenue: not built (securities law).
- Fiat rails for buyers, and selling task packages.
- Which Squads multisig holds the treasury vault, for the record (the vault's address is fixed in the program).
