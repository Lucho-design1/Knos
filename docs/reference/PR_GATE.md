<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Knos Gate: hidden tests on every outside pull request

**In plain words.** You keep some tests secret. Knos Gate runs them on each pull request from outside and says pass or fail in one check and one comment. The author never sees the secret tests, only how many passed.

1. An outside pull request arrives.
2. Cheat checks run on the diff: test edits, scope, data, workflows.
3. The sealed hidden tests run in a sandbox with no network and no token.
4. Gate posts one check and one comment, edited in place.
5. A signed receipt that anyone can verify offline.
*One pull request through Gate. A refused cheat stops it before any of its code runs.*

This page is not [GATE.md](GATE.md), which is the upgrade gate for a Solana program.

## Why

Maintainers are closing their doors because checking work now costs more than producing it (sources as of 13 Oct 2026):
curl ended its bug bounty on 31 Jan 2026 after valid reports fell below 5%; Google stopped OSS VRP submissions on 1 Oct
2026 ("vast majority not valid"); Sovereign Tech paused its bounty (790+ reports, about 80 accepted); tldraw
auto-closes external pull requests; Ghostty bans drive-by AI pull requests and uses Vouch; GitHub shipped settings to
disable or cap outside pull requests (13 Feb and 17 Jun 2026).

Every filter shipped so far judges WHO sent the work (Vouch, collaborator-only, pull request caps). None checks whether
the work is CORRECT against tests the sender could not see. Gate does that, and works beside those filters: a passing
Gate check can be the bypass signal a maintainer opts into (`pass_label`).

Unsolicited bot pull requests are merged far less often (Greenkeeper 32%, ASE 2017) than opted-in ones (Dependabot
about 70%, median about 4 hours, arXiv 2206.07230). Gate is opt-in by the maintainer and needs no wallet, no token and
no escrow.

## Install

Two files and two secrets, all in your repository:

1. `.knos/gate.yml` (`knos gate init` writes a starting one). The schema is `src/knos/gate/gate.schema.json`; an
   example is `actions/gate/example/.knos/gate.yml`.
2. Seal your hidden tests: `knos gate seal path/to/hidden-tests --secret-out hidden.b64` prints the sha256 for
   `hidden_tests.sha256`; store the bundle with `gh secret set KNOS_GATE_HIDDEN < hidden.b64` and delete the file.
   A secret holds at most 48 KB; a larger suite goes in a private repository (`source: repo`, pinned `ref`).
3. Copy `actions/gate/knos-gate.yml` to `.github/workflows/knos-gate.yml` and pin the action to a full commit sha.
4. Optional: a receipt key, `knos gate receipt keygen key.json` then `gh secret set KNOS_RECEIPT_KEY < key.json`.

The GitHub App (two clicks: install, pick repositories) is built but not registered: see "Register the App" below.

## What it checks, in order

| step | runs pull request code? | refuses when |
|---|---|---|
| config | no | `.knos/gate.yml` on the BASE commit is missing or invalid |
| outside only | no | (an owner, member or collaborator is not judged with `outside_only: true`; the check says so) |
| cheat checks | no | a rule of the cheat library refuses (REFEREE's `knos.cheats` when installed, else Gate's local rules: test edited, workflow edited, `.knos/` edited, hidden folder written, runner tampering, out of scope, data tampering, core path, no change) |
| hidden tests | yes, sandboxed | the bundle is not the sealed one, or a hidden test fails, or the re-run disagrees |
| public tests | yes, sandboxed | a public test fails |

`on_fail` decides what a refusal does: `comment`, `label` or `close`. In bounties mode a failing claim is always closed.

## What leaves the runner

Counts only: total, passed, failed, errors, skipped. Never a test's name, message or output. The suites' output and
reports are deleted before the artifact is uploaded, and every text Gate posts is checked against the hidden files'
lines first; a text that would quote one is not posted (`gate.leak_guard`).

## The sandbox, and its limits

The hidden tests run as a user of their own (`knos-sandbox`) in a network namespace with no network, with an
environment of PATH, HOME and LANG only: no GitHub token and no secret. That user cannot write the runner's files, so
it cannot reach `$GITHUB_ENV` or the Knos install that computes the verdict.

`setup` runs from the base commit before the pull request's code is on disk.

The Action fails closed: when the runner cannot make this sandbox (passwordless sudo and `unshare`), Gate stops with
exit 2 and runs nothing. The sandbox writes only a fresh folder of its own; the runner reads its report there without
following links and writes its own files elsewhere. A pass needs exit code 0 AND a report with no failure.

What it does not stop: the pull request's code runs in the same process as the hidden tests, so it can read them while they run and can try to fake their result, because the exit
code and the report both come from that process.

It cannot send them anywhere (no network, no token, no output shown), and the cheat library refuses the edits that fake a result (test runner configuration, `conftest.py`, `.pth`
files). A maintainer who needs more runs the hidden tests in a separate process or machine; that is not built in this version.

## Knos Receipt

Each run writes a receipt (`knos.receipt2`): the repository, pull request and commits; `mode` (hidden, or "public tests
only", said in words); the seal of the hidden tests; counts; the cheat library and its rules; the runner as the run's
environment reports it (not signed by GitHub in this receipt); the re-run; the verdict and its rule.

It is signed with Ed25519. `knos gate receipt verify FILE` checks it with Python's standard library alone
(`src/knos/receipt2/ed25519.py`, RFC 8032), from the JSON or from the saved receipt page. A valid signature by a key not
in `src/knos/receipt2/issuers.json` shows only that its holder signed.

The one listed key was generated for the v0.3.29 demo; it is not a founder key and holds no money.

An author can get a receipt for their own pull request to a repository without Gate: `knos gate receipt self` runs the
repository's own public tests and the cheat checks and signs with the author's own key. That receipt says "public
tests only" and that the author issued it.

## Bounties mode

`bounties.enabled: true` adds two things. A pull request that says it closes an issue ("Fixes #12") and fails Gate is
closed.

The escrow is the existing knos_pay one on Solana devnet (`knos fund-wallet OWNER/REPO#N AMOUNT`): the program pays the
merged pull request whose GitHub-signed run met the terms, and takes its fee for the treasury, a token account of Knos's
Squads vault.

`knos gate bounty quote AMOUNT` reads the fee from `config/fees.yaml` (through `knos.money.fees_config`) and `knos gate
bounty treasury MINT` names the fee account. Gate signs no payment and holds no key. Fiat on-ramps and off-ramps are a
founder decision.

## The demo, 13 Oct 2026 (synthetic tasks, devnet test tokens)

In the owner's new private test repository `drexthealpha/knos-v0329-gate` (a synthetic `slug()` task, three hidden
tests), with the Action alone. Every run used the `nonet,user` sandbox:

| pull request | Gate | run |
|---|---|---|
| #2 edits the public test | refused, `gate.test_edited`, closed; no test ran | [run 38432746562](https://github.com/drexthealpha/knos-v0329-gate/actions/runs/38432746562) |
| #3 correct fix plus `setup.py` | refused, `gate.out_of_scope`, closed | [run 38432754483](https://github.com/drexthealpha/knos-v0329-gate/actions/runs/38432754483) |
| #4 passes the public test only (claims #1) | refused, `gate.hidden_tests_failed` (1 of 3 hidden passed), closed | [run 38432762375](https://github.com/drexthealpha/knos-v0329-gate/actions/runs/38432762375) |
| #5 correct fix, then a second commit | passed (3/3 hidden, 1/1 public, re-run agreed), signed receipt; one comment, edited in place | [run 38432780017](https://github.com/drexthealpha/knos-v0329-gate/actions/runs/38432780017) |

The repository is private, so those links open for its owner only; its files (its main, ccf45c30) are in Knos as
[evidence/knos-v0329-gate](../../evidence/knos-v0329-gate/) (with the demo pull requests' heads in its SOURCE.json).

The bounty ran in the public test repository `drexthealpha/knos-e2e`, issue [#273](https://github.com/drexthealpha/knos-e2e/issues/273), with a test token minted on
devnet (no value), whose terms require the `Knos Gate` check and allow only `gate_slug.py`:

| step | evidence |
|---|---|
| 5.00 in escrow from the Gate demo wallet `H3iUwqY9aKKD1H9m5MmTYNcwcv8xUkGDDDfps6XjXtBP` | [funding transaction](https://explorer.solana.com/tx/4xurN74ZuqE8Uz9dqUhomSLMA5ko8LAr1gnS2Btafe9oiUHJwz2StfmF6dWBxGqX7VDDr9J1iKc2d242LiTV33fG?cluster=devnet) |
| a claim that fails the hidden tests is closed | [#274](https://github.com/drexthealpha/knos-e2e/pull/274), [run 38433820579](https://github.com/drexthealpha/knos-e2e/actions/runs/38433820579) |
| the correct claim passes Gate and is merged | [#275](https://github.com/drexthealpha/knos-e2e/pull/275), [run 38433833108](https://github.com/drexthealpha/knos-e2e/actions/runs/38433833108) |
| paid 51 s after the merge: 4.95 to the author's bound wallet, 0.05 fee to the treasury account `DkEX9RMi4NvJJTTr8463hctJo2tnS83g9Ti6sqEPCHT9` (owner: the Squads vault) | [payment transaction](https://explorer.solana.com/tx/2MbUhEUKdzLvyHe4WEd8cLqv1HGcKV91GGTNqF8y8EWN4jYTAw36n2nvsLBTsCw8ep9BBZLs3279TaN9Zobt9h1x?cluster=devnet) |

The author of both claims is the repository's owner (`outside_only: false` for the demo); there is no outside user.

## Register the App

The App's code is `github-app/server.py` (logic: `src/knos/gate/app.py`) and its manifest is
`github-app/app-manifest.json`. Nobody has registered it. The founder's steps:

1. Choose the host that will serve `https://<host>/webhook` and replace `REPLACE-WITH-YOUR-HOST` in the manifest.
2. Create the App from the manifest (GitHub: Settings, Developer settings, GitHub Apps, or the manifest flow
   `https://github.com/settings/apps/new?manifest=...`). Choose the name and whether to list it on GitHub Marketplace.
3. Download the App's private key and set a webhook secret. Keep both off the repository.
4. On the host: `pip install knos -r github-app/requirements.txt`, set `KNOS_APP_ID`, `KNOS_APP_KEY_FILE`,
   `KNOS_APP_WEBHOOK_SECRET_FILE`, run `python github-app/server.py --port 8787` behind TLS.
5. A repository using the App adds `github-app/knos-gate.yml` as `.github/workflows/knos-gate.yml` and its secrets.

## Commands

`knos gate init | validate | schema | seal | run`, `knos gate receipt verify | keygen | page | self`,
`knos gate bounty quote | treasury`.
