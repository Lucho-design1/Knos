# x402 `upto` on Solana: one ceiling, pay for the checks actually run

An agent will not prepay a pack of checks it may never use.

The x402 `upto` scheme lets it authorize a maximum once and be charged what it used: "transfers up to a maximum amount,
with final charges determined at settlement based on actual resource consumption"; single settlement, time bound,
recipient bound, settled amount at most the maximum
([`specs/schemes/upto/scheme_upto.md`](https://github.com/coinbase/x402/blob/main/specs/schemes/upto/scheme_upto.md),
read 14 Oct 2026).

**Does `upto` support Solana now?** In part, and the sources disagree on how much:

- The specification repository has only `scheme_upto.md` and `scheme_upto_evm.md` (Permit2); there is no
  `scheme_upto_svm.md` on `main` (14 Oct 2026).
- The x402 docs say SVM is supported through Solana's
  [payment-channels program](https://github.com/solana-foundation/payment-channels): the client locks the ceiling
  amount in an onchain channel (`open`) and the server settles "with a signed voucher (`settle_and_seal` +
  `distribute`)" ([docs.x402.org/schemes/upto](https://docs.x402.org/schemes/upto.md)).
- The public facilitator lists `upto` only for `eip155:84532` (Base Sepolia), not for Solana devnet
  ([x402.org/facilitator/supported](https://x402.org/facilitator/supported), read live the same day).

So Knos runs the Solana side itself, in the docs' "self-managed mode": Knos holds the receiver-authorizer key that signs
vouchers and submits the settlement; no facilitator is involved.

## The program (`CHNLxYvVA28MJP9PrFuDXccuoGXAx7jBacfLEkahyGsX`, same id on devnet)

Read from its source (`program/payment_channels/src`, `docs/003-program-instructions.md`); audited by Cantina, July
2026, per its README.

| step | instruction | Knos code |
|---|---|---|
| the agent holds the ceiling | `open` (1): channel PDA `["channel", payer, payee, mint, authorized_signer, salt, open_slot]`, held money in its token account, the payout splits' sha256 | `x402_upto.open_ix` |
| Knos checks the open before relying on it | decoded fields against the 402: payee, mint, signer, grace, splits, deposit, PDA | `read_open`, `check_open` |
| Knos settles what was used | Ed25519 precompile over the 50-byte voucher `[0x56,0x01] ‖ channel ‖ cumulative ‖ expires_at`, then `settleAndSeal` (4), then `distribute` (7): splits paid, the rest refunded, dust to the deployment's treasury | `settle_ixs`, one v1 transaction |
| the agent's own escape route | `withdrawPayer` (8) after a seal | `withdraw_payer_ix` |

The 402 entry (`x402_upto.requirements`) is x402 v2 `PaymentRequirements` with `scheme: "upto"`, the CAIP-2 Solana
network, `amount` = the ceiling, and in `extra` what an SVM client needs to build `open`. No SVM payload for x402
`upto` is published, so those field names follow the program's own HTTP notes (`docs/002-http-protocol.md`:
`channelProgram`, `gracePeriodSeconds`, `distributionSplits`).

## On devnet (14 Oct 2026, own test keys, synthetic Token-2022 mint)

- Open: channel `CDE781e7feCr1dTLwMJSvyCWEKxBsxKK6W2j2Wpcomc6`, ceiling 20 test units,
  [`4AUSfCqe…`](https://explorer.solana.com/tx/4AUSfCqeFVGNyoVKnqfJWwRibqJWXpziCCM9wTU32ErDEdpdPmZciStGP4aydTKQF1tRacJnxAnt9SBbtf3Potca?cluster=devnet).
- Settle 7 used, Ed25519 + settleAndSeal + distribute in one v1 transaction,
  [`eQykTt3a…`](https://explorer.solana.com/tx/eQykTt3a3kupeYtcCtxoyg7gPNP7V1PDPw3sWVSSwNXmkmsFBTvHscmWdh3ms2h3YMyx2D9saqU4nkqWGTTF6mL?cluster=devnet):
  the payer got 13 back, the payee 6.3, the lab's 10% split 0.7.
- The first open failed with the program's error 58 (`InvalidPayerTokenAccount`): the payer's token account did not
  exist yet. The script now creates it first; a client must too.

On mainnet the CDP facilitator is named by the docs as supporting `upto` on Solana; using it needs a CDP API key.

Tests: `tests/test_money_x402_upto.py`.
