# Integrations: what a bounty or work platform can take from Knos

No platform named here uses Knos, has endorsed it or has been asked. This page has the reusable pieces, and how a platform
would use them.

## The pieces

| Piece | Where | What it does | What it needs |
| --- | --- | --- | --- |
| The `knos-verify` action | [`.github/actions/knos-verify`](../../.github/actions/knos-verify/action.yml) | One step: reads a pull request from GitHub's own record and gives a verdict as JSON, a job summary and a pass or fail. It answers two questions. Does a "tests pass" or "CI is green" in the description agree with the checks on the pull request's latest (head) commit? Did each check you name pass on that commit or on the merge commit? | A job token that can read checks. No secret, no id-token, no wallet, no chain write. Knos is installed from PyPI at one exact version |
| The receipt verifier | [`integrations/webhook`](../../integrations/webhook/README.md) | `verify(evidence, jwks)` in one Python file and one TypeScript file with no dependency: checks offline that a Knos receipt matches the token GitHub signed, and that it is for the repository, pull request and payee the platform expects | The issuer's public keys, as the platform trusts them. No network |
| The "Knos-verified" badge | `knos.badge.verified(receipt)`; [`examples/receipt_consumer/show_badge.py`](../../examples/receipt_consumer/show_badge.py); `renderVerified` of [`web/badge.js`](../../web/badge.js) | Says one deliverable was accepted, links to the transaction the signature was verified in, and is drawn only from a receipt that passes every rule of [RECEIPT.md](RECEIPT.md) with the verdict accepted. It cannot be bought. A receipt that does not check is "insufficient evidence", never a rejection | The receipt, and nothing from Knos at run time |
| The reader template | [`examples/reader_template`](../../examples/reader_template/README.md) | A whole Solana program, in a workspace of its own, that performs one action, and only when a named CI workflow asked for it: for a platform that releases on chain | Two constants, `cargo build-sbf`, a devnet key |
| The badge | [`integrations/badge`](../../integrations/badge/README.md) | "paid on proof" beside a bounty: the SVG and the link to the public record of the payment | A payment the platform checked first |

An example workflow that uses the action is [`integrations/workflows/knos-verify.yml`](../../integrations/workflows/knos-verify.yml).
The tests of these pieces are [`tests/test_integrations.py`](../../tests/test_integrations.py) and
`node --experimental-strip-types integrations/webhook/test.mjs`.

What the action's verdict is not: it does not run the pull request's code, it does not judge the work, and a
repository's administrators can still change what a check name means. It says what GitHub recorded for a commit.

## How a platform would use them

The smallest useful integration is the same almost everywhere: the platform already waits for "merged"; it adds an
optional, off-by-default "and this named check passed at the commit". The check can be the repository's own test
job, or a job that runs `knos-verify`.

The platform reads the result from GitHub (a check run on the commit), so it takes no dependency on Knos. A
platform that also wants to show a payment Knos made can check its receipt with the verifier and show the badge.

## What is not done

The action has been run against a
stand-in for GitHub in the tests and not yet in a workflow on GitHub. The verifier's TypeScript file is tested with
Node 22; it has not been run in Deno, Bun or a Worker.
