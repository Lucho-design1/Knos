# Alpenglow: paid and final

**In plain words.** Solana devnet now runs Alpenglow, a new way for validators to agree. A payment there is final
about a second after Knos sends it, not 13 seconds later. Knos asks each cluster which way it runs and, on Alpenglow,
waits until a payment is final before it says "paid".

On a cluster that has not moved yet, nothing changes.

## How Knos tells

Knos asks the cluster's RPC `getAgGenesisCert` once per RPC address (`knos.platform.finality`):

| The answer | What it means | What Knos waits for |
| --- | --- | --- |
| a certificate `{block: {slot, blockId}, signature: {signature, bitmap}}` | Alpenglow is active | `finalized` |
| `null` | the cluster still runs TowerBFT | `confirmed`, as before |
| error -32601 "Method not found" | a node older than Agave 4.3, which cannot run Alpenglow | `confirmed`, as before |
| no answer | nothing is known | `confirmed`, asked again after 60 s |

Knos never decides by a date or a version string. A certificate is kept for the life of the process; a `null` is
asked again after 10 minutes, so a relay that runs through a migration switches by itself.
`KNOS_COMMITMENT` still wins when it is set; `KNOS_ALPENGLOW=on|off` lets an operator override the detection.

Sources, read 14 Oct 2026: the method page [solana.com/docs/rpc/http/getaggenesiscert](https://solana.com/docs/rpc/http/getaggenesiscert)
(no parameters; `null` while the cluster runs TowerBFT; -32601 on a node older than Agave 4.3); Agave `rpc/src/rpc.rs`
`get_ag_genesis_cert` at commit 722c8f4b, which reads the finalized bank; `@solana/kit` `packages/rpc-api/src/getAgGenesisCert.ts`.

Also read: [solana.com/upgrades/alpenglow](https://solana.com/upgrades/alpenglow) (under Alpenglow `confirmed` and `finalized` are the same state,
new code should use `finalized`, and `confirmed` will be deprecated and removed; target finality about 150 ms, "an expectation, not a
constant").

**What devnet said** (14 Oct 2026, `api.devnet.solana.com`, solana-core 4.4.0-beta.0): a certificate for block slot
504,148,999, block id `13f09ed2…de31677`, signed by 13 validators (the bitmap's set bits). Mainnet-beta (4.3.0)
answered `null`; testnet answered a certificate.

## What switched to `finalized` on Alpenglow

Every place Knos waited or read at a hard-coded `confirmed` now asks `knos.platform.finality`:

- sending and waiting: `knos.chain.Ledger` (blockhash, preflight, the wait, reads), `chain.wait` / `wait_all`, the
  fan-out ledger the relays use (escrow release, payouts, Gate bounty payments, refunds), the WebSocket wait;
- Knos Record anchors (`knos.record.anchoring`), x402 settlement confirmation (`knos.money.x402_exact`), the faucet;
- the readers: receipts rebuilt from the chain (`knos.receipt`, `knos.bundle`), statements, audit, observe and the
  ZK client ask the cluster once; the plan floor reads at its ledger's commitment; a ledger that only reads, the
  escrow history reader (`knos.records`) and the mainnet check never add a request of their own and read at
  `finalized` once the process knows the cluster runs Alpenglow (`finality.cached`), else at `confirmed`, which is
  the same state there.

The other `confirmed` words in the code are names of states (the relay queue's "confirmed", the five payment states)
or texts about spreadsheet formats; they are not commitments and did not change.

## Waits retuned

- The first look at a payment just sent comes after 0.25 s on Alpenglow (0.5 s on TowerBFT). Later looks stay at
  0.5 s: the public devnet RPC takes 40 requests of one method per 10 s.
- After a payment is reported, the job waits at most 10 s for `finalized` on Alpenglow (40 s, `FINAL_WAIT`, on
  TowerBFT). A payment Knos already waited for at `finalized` is final at once: nothing is asked again.
- The wait for a sent transaction keeps its own ceiling (`knos.chain.wait`), which is not the blockhash's life: with
  200 ms slots (SIMD-0525) a blockhash lasts about 33 s on devnet, measured on 14 Oct 2026 as lastValidBlockHeight
  minus the `confirmed` block height over the block rate ([DURABLE_NONCES.md](DURABLE_NONCES.md),
  `python -m knos.platform.blockhash`). A transaction that must wait for another signer uses a durable nonce instead.

## "Paid and final in N ms"

The payment comment on a pull request adds one line once the payment is final:
`Paid and final in N ms after it was sent to Solana.` A Record anchor keeps `commitment` and `final_ms`. The site's
live page and `stats.json` (`finality`) show the cluster's consensus and the measured figures below.

## Measured on devnet

Our own test traffic, labelled "internal dogfooding" everywhere (`docs/finality.json`, every signature listed there).
`scripts/alpenglow_latency.py` signs each transaction, subscribes to it at `confirmed` and at `finalized` over one
WebSocket, sends it through Knos's ledger, then runs Knos's own wait. 49 transactions on 14 Oct 2026, one machine,
the public RPC:

| Transactions | n | send to finalized, p50 | p95 |
| --- | --- | --- | --- |
| all | 49 | 1,205 ms | 2,449 ms |
| Knos Record anchors | 30 | 1,213 ms | 3,040 ms |
| escrow funding (knos_pay FundWallet, 60 s deadline, test mint) | 15 | 1,134 ms | 2,449 ms |
| escrow refund after the deadline | 4 | 1,249 ms | 1,322 ms |

The `confirmed` and `finalized` notifications came at the same moment for every one of the 49, which is the "same
state" the Alpenglow page describes. The figure includes the trip to the RPC and its notification, not only the
validators' vote. Knos's own polling wait returned at p50 1,852 ms and p95 3,798 ms (`KNOS_WS=1` waits on the
WebSocket instead).

No payout is in the sample: a payout needs a GitHub OIDC token of a signed workflow run. Of 15 test jobs, 4 were
refunded by this script and 11 by another relayer first.

## Transaction counts and slot streams

Knos's dashboards count Knos's own programs' transactions (`scripts/network_stats.py`), never the cluster's
transaction count, so vote transactions leaving blocks under Alpenglow change none of its numbers. Knos does not
stream slots, blocks, shreds or Geyser updates (it reads single transactions and uses `signatureSubscribe` only), so
there is no per-(slot, bank_id) buffer to add and no ticks are counted.
