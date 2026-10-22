# Durable nonces: sign an escrow now, send it later

A Solana transaction names a recent blockhash and is refused once the cluster's block height passes the
`lastValidBlockHeight` that came with it ([confirmation docs](https://solana.com/docs/advanced/confirmation): the most
recent 151 stored hashes).

The window is counted in blocks, so it shrank in seconds when devnet moved to 200 ms slots (SIMD-0525,
`proposals/0525-reduce-slot-times.md`: "any user-facing ... behavior measured in number of slots may become shorter in
wall-clock time").

**Measured on devnet, 14 Oct 2026** (`python -m knos.platform.blockhash`, raw output kept by the build): the
`confirmed` block height was 134 to 146 blocks (mean 143) below `lastValidBlockHeight` while it rose 232 blocks in
54.0 s (4.297 a second; `getRecentPerformanceSamples` gave 236 to 240 ms a slot).

A blockhash fetched at `confirmed`
therefore had **about 33 s** left, not the minute older pages assumed.

That is too short for a funder whose approver signs on another machine, a financier's assignment
([ADVANCE.md](ADVANCE.md)), a hardware or cold wallet, or an agent whose owner approves its funding.

A durable nonce replaces the blockhash with a value kept in a nonce account; the transaction's first instruction
advances it, so the signed bytes stay good until they land, and land once.

## Use

| step | call | who signs |
|---|---|---|
| make a nonce account | `python -m knos.platform.nonce create PAYER_KEY NONCE_KEY [AUTHORITY]` | the payer and the new nonce key |
| build the message | `knos.platform.nonce.message(ixs, fee_payer, nonce, authority, value, v1=True)` | nobody yet |
| first signature | `nonce.sign_part(msg, [funder])`, written with `nonce.encode` | the funder, on their machine |
| more signatures | `python -m knos.platform.nonce cosign TX_FILE KEY` | each co-signer, when they can |
| send | `python -m knos.platform.nonce send TX_FILE` (refused while a signature is missing) | nobody: the bytes are complete |

`nonce.still_good(ledger, tx)` says whether the nonce still holds the value the transaction signed over; once the
transaction lands it does not, so the same bytes can never pay twice. Messages are v1 by default (SIMD-0385: the
compute limit in the message, 4,096 bytes, no lookup tables, so the nonce account is always a static key as SIMD-0242
requires).

## On devnet (14 Oct 2026, own test keys, synthetic Token-2022 mint `4Fx2QgywyiAyHTMqkFRLEnF2hPW89MfWi9TEqwXjEYSa`)

`scripts/capabilities_devnet.py KEYDIR nonce` made nonce account `7XD6BDC2G676KQ85vkp34vgrSy8whk5EsvAGJJj9SZZJ`
([`5s2w28fa…`](https://explorer.solana.com/tx/5s2w28fa1B9wp2qdMaC8Jh5UQWyj2XJm1GRxXzeYjY38rstgpbstRB2TA4uZhemnJqYUw7oeUXPnKAfJKFcc8bWB?cluster=devnet)),
then had the funder sign a knos_pay `FundOrderWallet` alone and the relay add its fee-payer signature and send it 56.9 s later, well past any
blockhash's life:
[`3LT3NScV…`](https://explorer.solana.com/tx/3LT3NScVpHQLbrh7n1A7y7aFta8ZVm2aUUq3bifEk8pzwd2yYBm6Yy54N5dHjTwcQxq4mcoAULBwR5qM5wvcWibq?cluster=devnet)
funded order `GNqQRH9mZabN43vynzgFoJFRq7ETpuY8eujQYEGM8uyv`.

A second run 59.0 s apart,
[`618qYsba…`](https://explorer.solana.com/tx/618qYsba2M4EcAgk8kdVpVokTzVszH2zN4z1BhfqEn5d8NQFKkf3twpjebD1D3PQ8NXX6QzqAtvL3Nn9MrjK6Smg?cluster=devnet),
then read the nonce back: it had moved on, so those bytes can never land again.

Both orders hold 5 synthetic test units in a Token-2022 mint with no extensions (`python -m knos.platform.token22` passes it) and are refunded at their
deadline.

Tests: `tests/test_platform_nonce_v34.py`.
