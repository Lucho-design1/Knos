# Kora and CCTP V2: researchers with no SOL, funders with USDC on another chain

## Kora: gasless for researchers and agents

[Kora](https://github.com/solana-foundation/kora) is the Solana Foundation's fee relayer: a JSON-RPC 2.0 node that
checks a transaction against its operator's policy and signs it as fee payer, so a user holding only USDC, or nothing,
can still send. Methods used, from its `rpc-api.md` and OpenAPI document (read 14 Oct 2026): `getConfig`,
`getPayerSigner`, `getBlockhash`, `estimateTransactionFee`, `signTransaction`, `signAndSendTransaction`
(`transferTransaction` is deprecated as of 2.2.0). Audit status per `audits/AUDIT_STATUS.md`: Runtime Verification,
audited through commit `8c592591`; later commits unaudited.

`knos.money.kora`:

- `policy_problems(config, programs, mint)`: asks the node's own policy first (allowed programs, fee tokens, signing
  methods on), so a researcher is told before signing anything that the node would refuse.
- `send_gasless(kora, ixs, users, programs)`: the message names Kora's signer as fee payer, the researcher's wallet
  signs only for its own money, Kora signs and sends. v1 by default; `v1=False` gives a legacy message for a node
  that does not decode v1 (Kora's docs do not say whether it does).
- `gasless_ixs(...)`: adds the fee to Kora's payment address in the order's token, when the node charges one.

The node is the operator's (`KORA_RPC_URL`, optional `KORA_API_KEY`). **No Kora node was run for this build:** the
GitHub releases carry no binaries (14 Oct 2026) and building one means downloading its crates, which this build does
not do unasked. The tests use a synthetic node whose answers have the OpenAPI document's shapes.

## CCTP V2 into a Knos escrow (design, with its code)

Most institutional USDC sits on EVM chains. CCTP V2 burns it there and mints it on Solana (domain 5; Ethereum 0,
Arbitrum 3, Base 6; Fast Transfer supported with Solana as source and destination). On Solana, `MessageTransmitterV2`
is `CCTPV2Sm4AdWt5296sk4P66VBZ7bEhcARwFaaS9YPbeC` and `TokenMessengerMinterV2` is
`CCTPV2vPZJS2u2BBsUoscuikbYjnpFmbFsvVuJdgUMQe` on mainnet and devnet; "the token account must exist at
receiveMessage execution". Sources: developers.circle.com `cctp/concepts/supported-chains-and-domains`,
`cctp/references/solana-programs`, `cctp/references/technical-guide` (message layout) and
`api-reference/cctp/all/get-messages-v2` (Iris), read 14 Oct 2026. CCTP V1 is deprecated from 31 Oct 2026: V2 only.

The flow, in `knos.money.cctp`:

1. `plan(funder_token, scope, terms_hash, amount)`: what the funder's `depositForBurnWithHook` must carry:
   destination domain 5, `mintRecipient` = the funder's own USDC token account on Solana, `hookData` =
   `knos:order:v1` ‖ the order's scope ‖ its terms hash, so the burn names the order it pays for.
2. The funder burns with their own wallet on the EVM chain. Knos signs nothing there.
3. `attestation(source_domain, tx_hash)` polls Iris; `decode` and `check` refuse a message that goes elsewhere, to
   another account, for less, or for another order. The Iris reference page says "API key required"; the sandbox host
   answered without one on 14 Oct 2026 (a made-up hash got 404 "Message not found", not 401).
4. `receiveMessage` mints into the funder's account (anyone may submit it); the funder's `FundOrderWallet`, signed in
   advance with a durable nonce ([DURABLE_NONCES.md](DURABLE_NONCES.md)), moves it into escrow.

Not built yet: the Solana `receiveMessage` instruction itself (Anchor, with the token messenger's remaining accounts),
and no transfer was run: the EVM leg needs testnet ETH and testnet USDC, which Knos does not hold.

Tests: `tests/test_money_kora_cctp.py`.
