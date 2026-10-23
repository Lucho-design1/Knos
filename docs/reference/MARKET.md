# Prices, and what devnet can and cannot show

**Knos carries research across the valley of death: each step is paid only on verified proof.**

This page has the price book, what the program takes when it pays, and what is a demonstration on devnet. Knos runs
on Solana devnet and its money is test USDC.

No real money has moved, nobody has bought anything, and nothing here is charged today.

## The price book

Every price in this table is proposed. The Meter line is not what the program on devnet charges (see below).

| Line | Unit | Price | Who pays | Where it is enforced |
| --- | --- | --- | --- | --- |
| Check | pull request or artifact checked | free, forever | nobody | nowhere |
| Meter | evaluation | 100,000 a month free per organisation, then 0.002 USD | buyer | prepaid credits |
| Acceptance | dollar released or reconciled against a signed acceptance | 0.30%; by contract 0.20% on monthly value above 1M (the rate never goes below 0.20%); small tickets are netted: outcomes under 20 USD accumulate and settle as one release per payee per period, charged 0.30% of the netted amount with the 0.05 floor once per release; no cap | funder, on top of the amount | knos_pay at release (on chain: 0.30% and the floor; volume rates are a rebate by contract, off chain) |
| Record | lookup of a supplier's delivery record through the machine-priced API | 0.10 USD a lookup, paid per call by the caller (an agent, a marketplace, an underwriter) through the knos-order/x402 flow; the public record page and its file stay free | the buyer, marketplace or insurer reading it | `knos record serve` (anyone runs it; Knos hosts none) |
| Control | organisation, per year | Team 25,000; Business 100,000; Enterprise from 400,000 (not deliverable yet: it needs single sign-on, private deployment and support that do not exist) | buyer | contract |
| Pilot | one buyer, two suppliers, 30 days, one reconciled invoice | 2,500 USD, credited against year one | buyer | contract |

**The Meter on chain today differs from the price book.** The deployed `knos-meter` program on devnet charges
0.05 per evaluation after the first 10,000 of a month per owner (0.02 at the least under a Plan), in test USDC
(`programs-v2/knos_meter/src/lib.rs`, `FEE` and `FREE_PER_MONTH`). The price book proposes 100,000 free, then 0.002
USD (proposed, not charged anywhere).

Changing the program waits for an upgrade; until then the off-chain statement (`knos meter`) uses the price
book's numbers and the program uses its own.

**Who bears the Acceptance fee on chain.** On an order the funder pays it on top of the amount; on a job it comes out
of the amount (below, "What the program takes at release").

These are proposed prices. Nobody has paid any of them, and nobody has been asked whether they would. Nothing has
been sold; there is no legal entity to invoice from; on devnet every fee is test money and zero revenue.

**The rule: Knos never charges the party being rated.** A supplier pays nothing to be counted, to
keep its ledger, to verify a receipt or to appear in the Agent PR Index. The rated party never pays for its
rating, for a better score or for the resolution of a false verdict. The buyer pays, or nobody does.

**Connecting a supplier costs nothing.** There is no fee per supplier, at any number of suppliers: a fee there
would tax the reuse of a supplier by a second buyer.

Acceptance is one line where an earlier price book had two. It replaces the percentage on settlement and the
percentage on reconciled invoice value, and the cap that went with the second is gone.

Three things changed in this book:

- **The rate never goes below 0.20%.** The 0.10% tier above 10 million a month is withdrawn.
  **A 0.20% floor is a pricing policy, not a law.** Nothing enforces it but a contract Knos would have to win. It
  holds only while a buyer gets more from a signed acceptance than the fee costs and no alternative is cheaper in
  all: a billing company at 0.7% of volume with metering included, and a fork that charges nothing, are both
  alternatives.
- **Small tickets are netted.** A floor of 0.05 on every outcome is 5.05% of a 0.99 outcome. Outcomes under 20
  USD accumulate, and settle as one release per payee per period: 0.30% of the netted amount, the floor once.
- **Record is priced for a machine.** 0.10 USD a lookup, paid per call by whoever reads it. There is no
  subscription.

### The billing rule

**A month's invoice = Control + Meter + Acceptance on value reconciled off chain + Record lookups.**

- **Never twice.** Value released on chain paid its Acceptance fee there, to the program, at release. The
  invoice leaves it out. A customer-month says which accepted deliverables the program released.
- **The volume rates are marginal and by contract.** A Control plan is the contract. A month's accepted value is
  laid end to end, value released on chain first: the first 1,000,000 USD pays 0.30% and what lies above it pays
  0.20%. No rate is lower than 0.20%. Each deliverable pays the rate of the part of the month it lies in, and at
  least 0.05 USD. There is no cap.
- **0.20% is paid only on the part above 1,000,000.** It never applies to the whole month. A worked month under
  contract: 1,500,000 USD accepted. The first 1,000,000 pays 0.30%, which is 3,000. The other 500,000 pays 0.20%,
  which is 1,000. The month pays 4,000, or 0.27% of its value. It does not pay 0.20% of 1,500,000 (3,000). A
  test holds the code to this month (`tests/test_billing_defaults.py`).
- **No price rise without 90 days' notice, and never on an order already funded.** A rise is announced at least
  90 days before it starts. An order funded before that day pays the price in force on the day it was funded. On
  chain the program keeps each work order's fee as it was at funding: an order funded under knos_pay 2.1 keeps
  its fee after the upgrade to 2.2. Off chain, `billing.py` charges each deliverable the price in force on the
  day its order was funded (`price_at`), and refuses a list of prices with a rise on shorter notice
  (`check_prices`). The program cannot enforce the 90 days: a fee change on chain is an upgrade, and an upgrade
  waits only for its [time lock](../WORDS.md#time-lock). The 90 days are a term Knos would write into each contract; none is signed yet.
  `PRICES` in `billing.py` lists one price today: this book.
- **Small tickets are netted.** An accepted outcome under 20 USD that names its payee is not charged by itself.
  A payee's small outcomes of a period are one release: 0.30% of the netted amount, and the 0.05 floor once for
  the release. A hundred outcomes of 0.99 to one payee pay 0.30 netted, where one by one they would pay 5.00. One
  such outcome alone in a period still pays the floor. An outcome that names no payee is charged by itself.
- **The rebate.** The program takes 0.30% of every release whatever the month's volume. What the volume rates
  would not have taken is credited on the invoice. On devnet that is a credit against test money.
- No charge for a duplicate, an infrastructure failure or a retry Knos caused.
- An accepted deliverable is counted once, however many evaluations it took.
- A rejection that ran correctly is an evaluation, not an outcome: the Meter counts it and Acceptance does not.
- **Once, whichever rail pays.** A deliverable released by the program paid there; one paid by a bank transfer
  or any other rail pays on the invoice. The same deliverable listed under both is charged once.
- **A rail's own charge is not Knos's price.** A bank's wire fee or a network's fee is listed apart from the
  software price, in no line of it and not in its total (`rail_charges`; the invoice prints `payable` beside
  `total`).
- **The credit rule.** Value that is disputed or reversed never carries an Acceptance charge: in the month it was accepted it is left out of the reconciled value, and when it was accepted in an earlier month the fee it was charged, 0.30% of it unless the earlier invoice shows less, is credited on the next invoice.
- Limits are shown before work starts: `knos bill estimate` and the calculator on the site's Pricing page print a
  year from five inputs: the plan, evaluations a month, accepted value, the share of it released on chain, and
  record lookups.
- Commitments are sold by the year and drawn down by use. A price by the year is billed in twelve parts that add up
  to it to the cent; a month's Meter, Acceptance and Record charges come out of what is left of a commitment, and
  only what the commitment does not cover is charged on top. A commitment and the use it pays for are never both
  counted.

The rule is code: [`src/knos/billing.py`](../../src/knos/billing.py) takes a customer-month and returns the invoice
with every line and the rule that produced it (`knos bill explain month.json`).

The site's calculator and the Python are tested against one file of years and months worked by hand
([`tests/data/billing_vectors.json`](../../tests/data/billing_vectors.json)). No program on chain computes Control,
a Record lookup or the volume rates.

**Why Acceptance is a price on value.** A flat price per evaluation cannot grow with the value it accepts: an
evaluation that accepts a 12 USD change and one that accepts a 40,000 USD milestone both would cost 0.002 USD at the
Meter's proposed price.

Acceptance is charged on the dollar, once, when a signed acceptance releases or reconciles it: 0.04 USD
would be the rate on the first and the floor makes it 0.05; the second pays 120 USD.

**What the program takes at release, shown before funding.** One rate and a floor, for jobs and orders alike:
`fee = max(0.05, floor(amount × 30 / 10,000))` in the token's base units. Who bears it depends on what was funded
(`programs-v2/knos_pay/src/lib.rs`):

- **An order** (a work order: what `/knos fund` makes): the funder pays the fee on top of the amount
  (`order_fee`). The payees get the whole amount.
- **A job** (a bounty funded from a Balance or a wallet: what `/knos tip` makes): the fee comes out of the amount
  (`fee_of`), and is never more than it. The payee gets the amount minus the fee; the funder pays the amount only.

| release | fee | as a share |
|---|---|---|
| 5 | 0.05 | 1.00% |
| 20 | 0.06 | 0.30% |
| 100 | 0.30 | 0.30% |
| 1,000 | 3 | 0.30% |
| 5,000 | 15 | 0.30% |
| 100,000 | 300 | 0.30% |

A release under 16.67 pays the floor, which is more than 0.30% of it: 5 test USDC pays 1.00%. The relayer's tip
comes out of the fee and is never more than the fee. On devnet the fee is test money: zero real revenue.

Where each price is fixed:

- **Check.** Nowhere: it is free, and stays free. The claim check, the Stop hook, the MCP tools, the Agent PR
  Index and on-chain verification cost nothing, and they are the distribution.
- **Meter.** In prepaid credits. It moves no customer money: it counts evaluations. Sending the same evidence
  again is not another evaluation. An evaluation that rejects is billable, because evaluating it took the same
  work; a Knos failure is not. The proposed 0.002 would cover processing the attestation, keeping the evidence and reconciling
  the count. It does not cover running the customer's tests or an agent's inference: those run in the customer's
  own CI, on the customer's bill. `knos-meter` on devnet still holds an earlier price list's numbers (0.05
  per evaluation after 10,000 free, in test credits; [METER.md](METER.md)); the proposed price here would be set by
  contract.
- **Acceptance.** In `knos-pay`, at release: 0.30% and the floor, taken when someone is paid. An order's funder
  pays it on top of the amount, and a refund returns amount and fee; a job's comes out of its amount, and a refund
  returns the amount. Under a contract a `Plan` can lower the rate for one owner; the program's own
  bound is 0.10%, and the price book's contracts go no lower than 0.20%. No such contract exists. Bundling small
  payments (netting) happens off chain: on chain the smallest order is 5 test USDC, and each release pays the floor. Value a buyer and a supplier reconcile off chain is invoiced off chain at the
  same rate, by `src/knos/billing.py`, and needs no customer money on chain. On devnet an order holds between 5
  and 100,000 test USDC; a build for real money decides its own cap. The current programs (Knos's
  second deployment) can be upgraded only through a multisig with a public 8-day delay, at least until an outside
  review, so any change to these constants is
  public 8 days before it can run.
- **Record.** Through `knos record serve`, a server anyone runs and Knos hosts none of: a supplier's delivery
  record is also a static file, and the public record page and its file stay free. Nobody has bought a lookup.
  The price is for a lookup by a machine: an agent, a marketplace or an
  underwriter pays 0.10 USD for the call, through the same order flow that pays for work ([X402.md](X402.md)).
- **Control.** In a contract. Nothing on chain enforces it, and the software it covers is in this repository under
  the MIT licence. What is sold is policy, budgets, private repositories, statements, exports, and a party that
  answers for the service. That party does not exist yet. Team is one business unit; Business is several
  suppliers with approval workflows and accounting exports; Enterprise is not deliverable.
- **Pilot.** In an invoice, off chain: one buyer, two suppliers, 30 days, one reconciled invoice, and the findings
  as numbers. Its price is credited against year one if the buyer goes on. It starts in shadow mode: the count runs beside the
  invoices the buyer already receives and changes nothing. [PILOT.md](PILOT.md) is the offer in full.
- **Not offered: index data, an advance, assurance.** The Agent PR Index is free. An order can already hold back a
  share for a warranty period and return it if the work is reverted, and a payee can assign an order's payment to
  another wallet; pricing an advance or a warranty needs a history of losses, a licence and real money, and there
  is none of the three.

## Devnet is Knos's test mode

A payments company onboards a customer in a test mode first: integrate there, with money that is not money, and
change one setting later. Devnet is that mode for Knos.

Every integration starts here, and the evidence is portable: a receipt verifies from GitHub's signatures with
no chain ([RECEIPT.md](RECEIPT.md)), so nothing a customer keeps depends on devnet's history, which Solana does
not promise to keep ([clusters](https://solana.com/docs/references/clusters)).

| can be real while the programs stay on devnet | is a demonstration |
|---|---|
| Control, Meter, Acceptance on value reconciled off chain and the Pilot: software billed off chain in ordinary money. Nothing has been sold, and there is no legal entity to invoice from. | Acceptance at release: money held until the proof passes, then paid. The money is test USDC. |
| A Pilot on a buyer's own repositories and its real invoices. None has been run. | Every fee the program takes: test money, zero revenue. It is not sellable until a mainnet deployment, which is not planned before an outside review. |
| The count: evaluations of real work, signed by the forge, in ledgers each side keeps. | Cost, congestion and reliability under mainnet load and priority fees. |
| Use by accounts that are not Knos's, a supplier reused by a second buyer, a statement both sides compute. All zero today. | Security against an attacker who risks real money. |
| Records a customer keeps and verifies without the cluster. | Devnet as the ledger of record. It is not one. |

Until settlement is real, a customer pays its suppliers the way it already does, through its bank. Knos records
the settlement status of each deliverable as paid outside Knos, payable, held, refunded, or a devnet
demonstration, and says which.

**Tokenless.** Knos has no token and plans none. Revenue is subscriptions and fees in USD and USDC.

**Legal advice.** Holding money until the proof passes and paying it out for others may be money transmission, and the rules
differ by country and by state. Legal advice is needed before any real money moves. **None has been taken.**
[REGULATION.md](REGULATION.md) says what was read and what was not.
