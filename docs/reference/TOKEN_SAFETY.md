# Token safety: mints an escrow can trust, accounts a payout can reach

knos_pay holds a bounty in a token account of its own and pays it with one transfer. Token-2022 lets a mint carry
extensions that change what a transfer does, and some of them let somebody other than the funder and the judge decide
what happens to money in escrow. Since 0.3.31 Knos reads a mint's extensions before it holds a bounty in it
(`knos fund-wallet` refuses), and anyone can check a mint or a payee's token account first
(`src/knos/platform/token22.py`). The extensions are described at
[solana.com/docs/tokens/extensions](https://solana.com/docs/tokens/extensions) (read 14 Oct 2026).

| extension | on | why it matters to an escrow | Knos |
| --- | --- | --- | --- |
| PermanentDelegate | mint | the delegate can move or burn the tokens in any account, the escrow's too | refuses to fund |
| Pausable | mint | the pause authority can stop every transfer, the payout's too | refuses to fund |
| TransferHook | mint | every transfer runs another program with accounts the payout does not pass | refuses to fund |
| NonTransferable | mint | the tokens cannot move | refuses to fund |
| TransferFeeConfig (a fee above 0) | mint | the payee receives less than the terms say | refuses to fund |
| DefaultAccountState frozen | mint | a payee's new account starts frozen | refuses to fund |
| ConfidentialTransferMint, MintCloseAuthority, InterestBearingConfig, ScaledUiAmount | mint | amounts can move encrypted afterwards, the mint can be closed at zero supply, or wallets show a different number | warns |
| MemoTransfer (required) | payee's account | an incoming transfer needs a Memo instruction right before it; the payout carries none | the account cannot receive a payout |
| frozen | payee's account | a frozen account receives nothing | the account cannot receive a payout |

Classic SPL Token mints (test USDC among them) have no extensions; nothing changes for them.

## Check one

```
python -m knos.platform.token22 MINT_OR_TOKEN_ACCOUNT [...]      # one JSON line each; exit 1 when one is refused
```

An agent reads the same answer from the MCP resource `knos://token/{address}` ([MCP_SERVER.md](MCP_SERVER.md)).

## On devnet (14 Oct 2026, mints made for this test, synthetic)

| address | made with `spl-token` 5.3.0 | what the check says |
| --- | --- | --- |
| `DCtFdxWfiEPFp3TP4HqQ4N3LYvi7VXYA44D3HdshrTqX` | Token-2022, no extension | ok |
| `EtbPvaxwXBKUvcjfU5yAxNckzKAxSkifCwQkjVdcTxfS` | `--enable-permanent-delegate` | refused: PermanentDelegate; `knos fund-wallet ... --mint` stops before anything is sent |
| `EQcDmUQXjjbtbnSH7GcKzM1vkP1kKTLR4tkj22YF7aXH` | a 50 basis point transfer fee | refused: TransferFeeConfig |
| `CU3aX9mni6T3WPwHqgWHuSmKmgVgGWoNJUYsWebeo36W` | a token account with `enable-required-transfer-memos` (transaction `4r2pAwf8cTD86EPf2wcBj26Kne6PjStYNEQ1Q3i6NCruYPqcZzetMoxtAaAsjvQc4cS6NAkfHnSLztXiLo8su4TL`) | cannot receive a payout: MemoTransfer |

The payout's failure on a memo-required account follows from the Token-2022 rule (the Memo must be the instruction
right before the transfer, at the same level) and from knos_pay issuing no Memo; a payout into such an account was not
attempted on devnet.
