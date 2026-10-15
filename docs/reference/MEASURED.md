# Pay for a measured result

**In plain words.** Until now Knos paid when tests passed. This page is about paying for a result you can only see in
data: more support tickets solved without a person, more trial users who buy, less time to a first reply. The buyer
and the seller write the result down before the work starts, a share of the items is kept aside as a control group
chosen by a hash nobody can steer, and the money is split into tiers that pay only when the measured improvement over
that control group is large enough, at an agreed confidence. Nothing on Solana changed for this: the measurement runs
as a pinned GitHub workflow, and the existing escrow pays each tier on GitHub's signed word that it passed.

Everything shown below ran on devnet with **SYNTHETIC** (made-up) support tickets and a test token worth nothing.
Nobody has bought a measured result through Knos.

## Why this needs more than "tests pass"

A buyer who wants to pay for a result has to say exactly what the result is, know the most it can cost, agree with the
seller on what the seller caused, and not pay for something that would have happened anyway. Each part of the outcome
spec answers one of these:

| The question | What answers it |
|---|---|
| What exactly is the result? | `metric`: a formula over one row of the buyer's own data, and the `window` it is counted in |
| What is the most it can cost? | `price.cap`: the total escrowed; the tiers add up to it exactly and nothing above it can be paid |
| What did the seller cause? | `control`: a share of the items (20% unless the spec says otherwise) handled the old way; only the difference counts |
| What if the world moved anyway? | the control group lives through the same window, so a change both groups saw cancels out |
| How sure must we be? | `success.confidence`: a tier pays when the *lower* bound of the lift's confidence interval reaches its bar, not the average |

## How it works, in six steps

1. **Draft the spec.** `knos outcome draft "Our AI agent should resolve more tickets without a human" --sample tickets.csv`
   reads a sample of the data and writes a draft `outcome.yaml` from a template. Nothing leaves your machine. With
   `--llm --llm-key-env ANTHROPIC_API_KEY` Claude drafts it instead, with your own key; the draft is checked against
   [the schema](../../schemas/outcome.schema.json) either way. A draft marks every value it cannot know with `EDIT`.
2. **Both sides sign it.** `knos outcome sign outcome.yaml --role buyer --keypair buyer.json` (and `--role seller`)
   signs the spec's hash, `knos outcome comment` prints the comment that puts the hash and both signatures on the
   orders' issue. `knos outcome verify-signatures` checks them.
3. **Lock and pin.** `knos outcome lock outcome.yaml --history data.csv` writes `outcome.lock.json`: the spec's hash,
   the window, the salt, the control share, the hash of the measuring code, the hash of the data dated before the
   window, and one order per tier. Commit the spec, the lock and [`prove.yml`](../../examples/outcomes/measured-support/prove.yml.in);
   that commit is the pin.
4. **Fund one order per tier**, from the buyer's wallet, before the window opens. Each tier is an ordinary `knos_pay`
   work order whose terms carry the spec's hash and the tier's bar, pinned to the repository's `prove.yml` at that
   commit (`knos outcome tiers` lists them and the total with fees).
5. **Measure** after the window closes: start `prove.yml`. Its first job calls the reusable
   [`knos-outcome.yml`](../../.github/workflows/knos-outcome.yml), which reads the window's data, recomputes who was
   in the control group, compares the two groups, computes the lift and a bootstrap confidence interval with the
   spec's fixed seed, runs the cheat checks, uploads `result.json` and passes only when the bar was reached. Its second
   job asks GitHub to sign one token per tier that passed, plus one naming the result's hash.
6. **Get paid, or get refunded.** Anyone relays the tokens: `knos_oidc` checks GitHub's signature on Solana and
   `knos_pay` pays that tier to the seller. A tier whose bar was not reached is never signed for, and its money goes
   back to the buyer after the deadline, as for any order.

## The control group nobody can steer

An item is in the control group when the first 8 bytes of `sha256("knos-outcome:v1:" + salt + ":" + item id)`, read
as a number between 0 and 1, fall below the control share. The salt is public and written into the spec, which is
signed and hashed into every order before the window opens. Anyone can recompute every item's group:
`knos outcome assign outcome.yaml --data tickets.csv`. Nothing random is drawn when the measurement runs.

## The numbers

- **Lift** is `(treated − control) / control` (relative) or `treated − control` (absolute), reversed when lower is
  better (time taken).
- **Confidence.** Both groups are resampled with replacement, each on its own, as many times as `bootstrap.resamples`
  says, with the seed `bootstrap.seed` (Python's Mersenne Twister, so the same data and seed give the same interval
  on any machine). The one-sided lower bound at confidence *c* is the (1 − *c*) quantile of the resampled lifts. A
  normal-approximation interval is printed beside it as a cross-check, never used to decide.
- **Tiers.** A tier passes when that lower bound is at least its `min_lift`. The command, and the workflow job, exit
  0 only when nothing was refused and the bound reached `success.min_lift`.

`tests/test_outcome_stats.py` holds the hash split, the lift and the interval to known answers.

## What the measurement refuses

Each refusal names a category that the cheat library and Knos Record share:

| Category | What it catches |
|---|---|
| `spec_hash_changed` | the spec now is not the one hashed at funding (a bar lowered, a formula edited) |
| `window_changed` | the window was moved |
| `salt_changed` | the salt was changed, which would move items between groups |
| `control_drift` | the share was changed; the observed control share moved more than four standard errors (items deleted from one group: with 10,000 items, deleting 900 of the treated group's failures is caught, deleting 100 is not); or the data's own "who handled it" field disagrees with the hash split |
| `measurement_code_drift` | the measuring code is not the code named in the lock (checked twice: by `sha256sum` in the workflow before any of the package runs, and by the package; a lock naming no code is refused) |
| `data_tampering` | rows dated before the window changed after funding; an item id appears twice |

A measurement before the window has closed, or with fewer than 30 items in either group, is refused too. Two more
checks are the escrow's own and need nothing from this workflow: a token from any commit other than the pinned one is
refused by `knos_pay` (error 86), and a spec edited after funding gives other terms, so its token names another terms
hash and is refused (error 87). When the cheat library (`knos.cheats`) is installed its outcome rules run too.
`tests/test_outcome_measure.py` refuses each known-bad case.

## Who can stop a payment (the trust model)

Say this before anyone funds an outcome: **the buyer holds the data and the button.** The data are the buyer's own
record (a file in the buyer's repository, or the buyer's endpoint), and only an account with write access to that
repository can start `prove.yml`. So a buyer who never starts the measurement, or withholds or breaks the data, is
never signed for, and every tier goes back to the buyer after the deadline. Nothing in this version stops that; what
it gives the seller is:

- **Time.** `dispute_window_days` is used at funding: `knos outcome` refuses to fund orders whose deadline comes
  before the window's end plus that many days (`escrow.fund_ixs`), so the seller has that long, after the window, to
  see a measurement run, ask for one, or take the dispute elsewhere.
- **Evidence.** The spec both parties signed, its hash on the orders' issue, and the pinned workflow mean anyone
  with the data can rerun the measurement and show what it would have paid.

It is not an arbiter. A seller who needs protection from a buyer who will not measure needs data the seller can also
read (a shared endpoint) or terms outside this version; both are open questions for the founder.

The other direction is what the checks are for: the seller cannot edit the buyer's record, so the cheat checks look
for changes the record itself would show (a moved window or salt, an edited history, items moved between groups, a
share that drifted). Small selective deletions inside the buyer's own data are only caught by the share when they are
large (see the table above).

## Why the token comes from `prove.yml`, not from the reusable workflow

`knos_pay` pays an order only on a token whose workflow file is `prove.yml` at the commit the order pinned. A job
inside a reusable workflow is signed under the reusable file's name, so a token asked for there would be refused. So
the reusable workflow only measures and outputs the audiences; the buyer's own `prove.yml` asks for the tokens in a job
after it, checks each audience against the lock first, and runs no code from the repository. `prove.yml` names the
measuring workflow at a commit and the order pins `prove.yml`'s commit, so the measuring code is pinned too.

## Knos Record

Every measurement appends one public `verification` entry (spec hash, domain `outcomes`, passed or refused, each
tier's result, the lift and its bound) and one `cheat` entry per refusal, and every funding, payment and refund one
entry with its devnet signature, through Knos Record's API ([RECORD.md](RECORD.md)). Entries hold hashes, amounts and
signatures only: no item ids, no rows, no token, no key, and `synthetic: true` for made-up data.

## The devnet demo (SYNTHETIC)

[`examples/outcomes/measured-support`](../../examples/outcomes/measured-support/) runs the whole path: 300 made-up
tickets before the window and 10,000 inside it, an "AI agent" handling the treated ones, three tiers (relative lift of
5%, 10% and 20%; 5, 10 and 15 test units). The chances of success are chosen parameters of the generator, so the lift
is chosen too: the demo shows the mechanics, and says nothing about any real agent. `demo.json` beside it holds every
transaction signature and what the chain said when it was read.

**What ran (13 October 2026, devnet).** Repository `drexthealpha/knos-v0329-outcomes` (private, the runner's own;
id 1417494699), issue 1, pinned commit `509485fb3b690a946e2a260079cf51cca307f1b5`, spec hash
`1812b0de5e01c6252c78500ba50fb676f180b7abd9b4b44d5720165e11fdb361`, window 17:05:12 to 17:15:12 UTC, data commit
`b59b30f3706987ea7a3426917add1ac9a19662d2`. GitHub run 38437227091: `measure` passed, `sign` asked for two tier tokens.
Both commits are in Knos, byte for byte: the pinned one as [evidence/knos-v0329-outcomes](../../evidence/knos-v0329-outcomes/),
the data as [evidence/knos-v0329-outcomes-b59b30f3](../../evidence/knos-v0329-outcomes-b59b30f3/) (the repository is private).

| | treated (agent) | control (people) |
|---|---|---|
| tickets in the window | 7,991 | 2,009 |
| resolved without a person | 0.5267 | 0.4460 |

Relative lift 0.1810; one-sided lower bound at 95% confidence 0.1304 (1,000 resamples, seed 20261013); result hash
`4f7a28b12790c709212323aebc30d80aa6280f5dbf093793d580f97f01713951`.

| Tier | Bar | Amount | Funded | Outcome |
|---|---|---|---|---|
| lift-5 | 0.05 | 5 | `bz6GBzKFoDdsjApdK1L9v6k534vjHxL3VLoiKgSdZWzyTY9h8r3gbULWLdwNh9vFiiis7Zzsm2QhadeqxRj5S3K` | paid: verified `62fqUyLZ2jWbXvL5B9tB6phBeCWrxamhsMjPqJt1VQU1iEK2zeJuVQU3RjPsrzU9CsLecW6vsiG6VVX3NWDqokVx`, `3ADtQduR7Rwzw8VQu54NAm978zTo5iQQUb23Er6mkF2MvFyHa7gMYWKqkNhrU9zZy7ASosG4h4RgkXT4EzAqYsN6`; paid `3jwVAHzY34Kg2pfHNwHDgy5B2iw4BeQPZP5YBrBxH2TmVR2DnegSyKDnKjXx8W6qbiJRgDW9g6t9vuxnJimBc93c` |
| lift-10 | 0.10 | 10 | `5vvjknjCVra5cRAwktQp3s1mi2GWwRMYjAwi58b153GK9hQM8sMfuD4vec89sPzRMU1HpN6bvvQmYmJuKoWxCNrq` | paid: verified `Arq1HjX38w7Q41hLg34xYwBh2ELjxcMQJi4aCpnm9U3WbAeSkjAAmYCXfRDrP8gkhgFsPFg3jhY2e2ALHJwvFKn`, `3ciU6jyBN1utGrEoYFKT4k3pHVV8pnGnEwVveV9q2PWHgZfoftjbxpPB9sSne7VTDnDzrtMuHPNSsVVGewD7f8FA`; paid `MNtvKckRKTzDde9ZwhXK634ZCLpyRJ7tMLnVr1Rus4T5TF5Ceegwp24anVcyF2mzdDmHJTaXsUdq1jaGx4BoZGv` |
| lift-20 | 0.20 | 15 | `2yQrtp97tq92scSJxsnhjHjEacz4AJwHuyAvYqeUXih8w511F9dwMMdaRCiMBNpysmwdeEE3jqfavy1hwip7e7iZ` | not signed for; refunded after its deadline by the public relay: `2js1rHv2jrGMNjVLQftczVWs59SyQj6oxyBE15dmGGFrqsEkqRdjHTZvigqVZivmDyMrP9BUH1EMj3nr99rqu1Kt` |

The seller's account held 15 test units after it: the two tiers reached, and nothing of the third. An earlier round
(pinned commit `aa9e366c`) is in `demo-round1.json`: its measuring job failed before measuring (the workflow could
not fetch the data branch of a private repository; fixed since), so nothing was signed and the public relay refunded
all three tiers after their deadline, as designed. The fees were the escrow's own (`knos_pay` order fee, 0.05 per
order at these amounts).

## What it does not do

- It cannot tell whether the data are true. It reads what the buyer's repository or endpoint serves; the buyer owns
  that record. The checks catch edits to the history, moved items and a drifting control share, not a fabricated feed.
- A tier is all or nothing. A result between two tiers is paid the lower tier.
- The parties must agree on the metric before the window. Knos does not judge whether the metric is the right one.
- No buyer has used it. The demo's buyer and seller were one person's own accounts.
- The buyer can block a payment by not measuring (see "Who can stop a payment"). The demo's signed spec says
  `dispute_window_days: 7`, but it was funded before funding checked it, with a deadline 30 minutes after a window of
  minutes; `demo.py` now writes 0 into a new demo's spec so that the check and the demo agree.
