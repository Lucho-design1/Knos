# Spending limits on the treasury: bounded costs without a vote each time

Knos's fees land in a Squads vault and move only by a vote of its members ([GOVERNANCE.md](GOVERNANCE.md),
[MONEY.md](MONEY.md)). Running a research market has small recurring costs: a lab's sample fee the referee approved,
refilling the test-token faucet, topping up the relay's fee payer.

A Squads v4 spending limit lets named keys, which "don't have to be members of the multisig", move at most an amount of one
mint per period (one time, day, week, month), only to listed destinations, from one vault (IDL `squads_multisig_program`
2.1.0, `ConfigAction::AddSpendingLimit`, `state/spending_limit.rs` in
[Squads-Protocol/v4](https://github.com/Squads-Protocol/v4), read 14 Oct 2026).

For an autonomous multisig, as both of Knos's are, the limit is a config transaction the members vote on:
`config_transaction_create` (AddSpendingLimit), `proposal_create`, `proposal_approve` until the threshold,
`config_transaction_execute` with the new SpendingLimit account, the rent payer and the system program.

`knos.platform.squads` builds each instruction (Anchor discriminator + Borsh), reads multisig and spending-limit
accounts back, and `plan(...)` returns the unsigned instructions and the steps. No Knos key signs any of it.

## On devnet, on a multisig of the build's own fresh test keys (14 Oct 2026)

| step | transaction |
|---|---|
| a 2-of-2 multisig of two fresh test keys, `7rPYyMdva4DAehkMMNgQjwPkdCyvpyj3KgCN9V2WkKxc` | [`PpcKempX…`](https://explorer.solana.com/tx/PpcKempXjpxsi4UbRwieShqhxPkcWw5hJcxNqnXwumRdUQKstfiHhGvuKQzvJXurHXhPvHp6RevYdBbtZhV5CjR?cluster=devnet) |
| config transaction + its proposal + the first vote | [`5mToKEaV…`](https://explorer.solana.com/tx/5mToKEaVgFSf7oaqN8NyaoroYdjPBbpHc8khxDw4FE9sfxtU3AHxjSTRn4o4Z1gqv8j4LoU5z17CjzJa2zcpkCdJ?cluster=devnet) |
| the second vote | [`5K81mfdY…`](https://explorer.solana.com/tx/5K81mfdYyGLAmGP2PG5zV1zxfC5v252h8ymBqXrGjo9JRCqff7ecVTcsJzQCgjj5UCMAS4fbNVJyqzcLNdx9aei4?cluster=devnet) |
| executed: limit `AzTJWjBt1SXye7oU71Hu37Z6CiZzWWN2SyqrMCTpCFYe`, 5 test units a day, one spender, one destination | [`4ewSHQeL…`](https://explorer.solana.com/tx/4ewSHQeLqqZeWaph61Qvj4j5zPNgrr9tU2mkj3zrvYPo95cLcFatQhwbs9FD1cCY2qjfKxKnRwHY7UiwFU5jgG9a?cluster=devnet) |
| the spender (not a member) pays 3 to the destination | [`mTahraiw…`](https://explorer.solana.com/tx/mTahraiw6pwCd98mETr6GKCU1U4i95inDi9YPwKaKoS8ZzfqzxSP6vxS6Fucrnk19HL18mMjYsuwyYdRKfmL5aB?cluster=devnet) |
| a second 3 the same day | refused by the program (Anchor error 6026), 2 remaining |

## The founder's steps for Knos's own treasury

Knos signs nothing here. One fact must come first: the treasury vault `4G3cznCnwCUPBCZwzKiLupjdgB5pSoCcGWNGuFv4TYFo`
(`config/fees.yaml`) is not vault 0 to 255 of either multisig named in `programs-v2/program_ids.json` (checked by
derivation for this build), so the founder names the multisig that owns it.

1. Decide the limit: mint (test USDC on devnet), amount per period, period, the spending key (a fresh key held by the
   operator, not a member key) and the destinations (the faucet, the relay's fee payer, a lab's account). Empty
   destinations means anywhere: do not leave it empty.
2. Print the plan, which signs nothing:
   `PYTHONPATH=src python -c "from knos import chain; from knos.platform import squads as s; from solders.pubkey import Pubkey as P; m=P.from_string('MULTISIG'); print(s.plan(m, s.read_multisig(chain.ledger().account(m)), P.from_string('CREATE_KEY'), P.from_string('MINT'), AMOUNT, 'week', [P.from_string('SPENDER')], [P.from_string('DEST')], P.from_string('YOUR_MEMBER_KEY')))"`
3. With your own member keys on your own machine: create the config transaction and its proposal (instructions
   `create` and `propose` of the plan), approve it with as many members as the threshold asks, wait out the time lock,
   execute it with the spending-limit account the plan names.
4. Read it back: `knos.platform.squads.read_spending_limit` on the limit's address.

Tests: `tests/test_platform_squads_v34.py`.
