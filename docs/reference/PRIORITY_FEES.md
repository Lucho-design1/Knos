# Priority fees sized to the work, and a WebSocket wait

Two switches for whoever runs a Knos relay or sends Knos transactions (`src/knos/platform/priority.py`). Both are off
unless set, so nothing changes for anyone who does not ask.

| variable | what it does |
| --- | --- |
| `KNOS_PRIORITY=auto` | before a transaction is sent: a simulation measures the compute units it uses, the limit is set to that plus 15%, and the price is the 75th percentile of `getRecentPrioritizationFees` for the accounts it writes |
| `KNOS_PRIORITY=<number>` | the same limit, at that many micro-lamports a compute unit |
| `KNOS_PRIORITY_MAX` | the most it will pay a unit (default 200,000 micro-lamports) |
| `KNOS_WS=1` | wait for confirmation with one `signatureSubscribe` over the cluster's WebSocket, after one status read, instead of asking `getSignatureStatuses` every 0.4 s; falls back to asking if the WebSocket cannot be used |

Why the limit matters: a priority fee is paid on the compute-unit LIMIT, not on what was used
([compute budget](https://solana.com/docs/core/fees/compute-budget), read 14 Oct 2026). Knos's default limit is the
most a transaction may use, 1,400,000 units. On a v1 transaction the two compute budget instructions do nothing;
`knos.chain.message_v1` already reads their values into the message's own limit and priority fee, so the same
setting serves both formats.

Why the WebSocket matters: the public devnet endpoint allows 100 requests in 10 seconds per address
([clusters](https://solana.com/docs/references/clusters)); polling a slow payout spends that allowance.

## On devnet (14 Oct 2026, memo transactions from a test wallet, synthetic text)

| setting | transaction | fee (lamports) | units used |
| --- | --- | --- | --- |
| `auto` (the devnet estimate was 0: limit only) | `5DQE7BExKrFDLz1MpxF8bs5PTcaRvJrDq784QE7JavGqq6pt1Cdhq2U5JDjfJsntmPfVfVpfUyctQYvAhLuqzMPH` | 5,000 | 34,772 |
| `5000` micro-lamports a unit | `3fbKZsan5n4Fto5o4AnE8vvisYcvYYHyaW4jR9CkWpvTWRmkttR9GXQXvy2UPsqacA2SFjZiHW3L7JheehxV2Wvg` | 5,202 | 34,922 |

The second paid 202 lamports of priority fee on a limit of about 40,400 units. At the same price on the old limit of
1,400,000 units it would have paid 7,000. A `signatureSubscribe` over `wss://api.devnet.solana.com` for
`2YzenZTX7aAUFoWeF3sm5jEXkpbqSxbeBgc7Gb1D29r8gRHwKsBA1EASwSPQAZA2nJUtz3XLPBUXp6kX9QG8QoLW` was notified 1.6 seconds
after the transaction was sent (one run, not a benchmark).
