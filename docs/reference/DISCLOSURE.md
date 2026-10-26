# Disclosure

This page says what was built when, what came from elsewhere, and what does not exist yet.

The repository's git history shows all of it, and [CHANGELOG.md](../../CHANGELOG.md) has every release.

## What was built when

The short form, by date. Times are UTC and are the commits' own (`git log`); a release's date is its release
commit's.

| when (UTC) | what |
|---|---|
| 1 Sep 2026 | the public repository's first commit |
| 1 to 7 Sep 2026 | Knos 0.1.0 to 0.1.8: shared local memory for coding agents, a different product |
| 7 to 12 Sep 2026 | more work on that product, never released |
| 13 Sep 2026 | two experiments begun outside this repository; none of their code is here |
| 14 to 29 Sep 2026 | automatic evidence commits, and 3 by hand for Knos 0.1; the two experiments ran until 28 Sep |
| 30 Sep 2026, 03:07 | Knos 0.2.0 (commit `54ce98a`), then 0.2.1 at 03:43 and 0.3.0 at 19:19 |
| 1 Oct 2026 | Knos 0.3.1 (08:57), 0.3.2 (09:55), 0.3.3 (12:06), 0.3.4 (15:12), then 0.3.5 to 0.3.7 |
| 2 Oct 2026 | Knos 0.3.9 (04:56), 0.3.10 (09:51: the first deployment on devnet), 0.3.11 (14:10, commit `f3dfd3d`) |
| 3 Oct 2026 | three pull requests by another account merged; Knos 0.3.12 (16:13: the second deployment) |
| 4 Oct 2026 | Knos 0.3.13 (09:02), Knos 0.3.14 (21:46, commit `6eb81dd`) |
| 5 Oct 2026 | Knos 0.3.15 (10:49, commit `72511b3`) and 0.3.16 (23:47, commit `50ecb05`) |
| 6 Oct 2026 | Knos 0.3.17 (20:00, commit `f03ec51`) |
| 7 Oct 2026 | Knos 0.3.18 (07:40, commit `f8bcd9d`) and 0.3.19 (15:47, commit `155b570`) |
| 8 Oct 2026 | Knos 0.3.20 (01:04, commit `fb77f4f`); the interface crates published on crates.io and the JavaScript client on npm (`npm install knos-settle`, [knos-settle](https://www.npmjs.com/package/knos-settle) 0.3.20) |
| 8 Oct 2026 | Knos 0.3.21 (09:59, commit `042b7dea`) and 0.3.22 (19:28, commit `c4350c97`) |
| 9 Oct 2026 | Knos 0.3.23 (04:59, commit `852e6135`) and 0.3.24 (13:20, commit `fb4217c1`) |
| 10 Oct 2026 | Knos 0.3.25 (02:43, commit `095f52ae`) |

To list the releases with their times from a full clone:

```
TZ=UTC git log --date=format-local:'%Y-%m-%d %H:%M' --format='%ad %h %s' | grep ' Knos 0\.'
```

## Before Knos 0.2

- **Knos 0.1.0 to 0.1.8**, 1–7 Sep 2026: a shared local memory for coding agents, with claims on topics and a guard
  on edits, built on Sibyl. It is a different product from the one here.
- Almost none of Knos 0.1 is in the tree. Its memory server, claims, edit guard, payment gate and integrations were
  removed in 0.2.0 and 0.3.10. They remain in the git history.
- One dependency carries over: Sibyl's memory client, which the judge and the local hook still use.

## The releases since

- **29 Sep – 2 Oct 2026, Knos 0.2.0 to 0.3.9** (first commit 30 Sep). 0.2.0 was built on top of 0.1.8. These
  versions tried claims enforced at edit time across agent vendors, agent budgets, a jobs market with held money,
  the Stop hook, the Agent PR Index, and a first payment program that verified GitHub's signature on chain but whose keys
  and workflows were registered by an admin. They are kept as they stood at 0.3.9 in
  [the tag `archive/labs` of drexthealpha/Knos](https://github.com/drexthealpha/Knos/tree/archive/labs), unmaintained. The Stop hook, the index and
  the judge are here.
- **Knos 0.3.10** (2 Oct 2026): the first deployment. Its two programs have no admin (`knos-oidc`, `knos-pay`), were deployed
  on devnet with no upgrade authority, and nobody can change them; payment to a GitHub account; the claim; the merge and tests modes with a veto
  window; the gate on every bounty pull request; the sandboxed judge for Python, Node, Go and Rust and its
  black-box mode; the relay; the JavaScript client; the site.
- **Knos 0.3.11** (2 Oct 2026): no change to the programs. A merge pays only when the pull request's claims hold
  at the merged commit; an agent's pull request pays the person who ran it; the check alone, with no money;
  `knos claim`; `knos mcp`; the interface crate, the IDLs and the npm tarball; every action pinned to a commit.
- **Knos 0.3.12**: the second deployment (`programs-v2`). Terms fixed at funding; no veto; payment straight to a
  wallet, in the transaction that verifies the pay token; balances funded from a wallet and spent by comment; classic
  and Token-2022 mints; signing keys that wait a day and expire; a guardian that can revoke a key or pause new
  funding for at most 7 days. It is upgradeable only through a multisig with a public 8-day delay, until an
  outside review. The first deployment keeps working for jobs funded on it.
- **Knos 0.3.13**: an upgrade of the second deployment through that multisig, and two new programs. Work orders in
  place of single bounties: each with a token account of its own, the fee paid by the funder on top of the amount,
  funding of any public issue from a wallet, standing orders, splits between payees, holdbacks and warranties,
  cancellation with notice, organisations as payees, and a payment that can be assigned. Attestation after a merge
  from a repository of the seller's own. `knos-meter`, which counts evaluations GitHub signed and holds no customer
  money. `knos-passkey`, a wallet made from a passkey. Signing keys of any RS256 issuer in the verifier. A policy
  file, statements and exports, and screening of payout addresses. Drills of the recovery paths on the deployed
  bytes.
- **Knos 0.3.14**: a correction and what follows from it. The payment program build that 0.3.13 proposed let one pay token
  pay a second order funded later for the same issue; it was found while the proposal waited out its time lock (then 48 hours), before the
  build ran, and that release withdrew that proposal and proposed a corrected one, in which every signed token is
  accepted once by one marker rule ([SECURITY.md](SECURITY.md), section 15). Also: overflow checks in release
  builds of every program; fee tiers in place of one rate, and a devnet cap of 100,000 per order; a batch mode of
  the meter with a seller's own count; funding from a passkey wallet; orders of GitLab projects; a hermetic judge
  by image digest; a feed of upgrade proposals; and the documents [INVARIANTS.md](INVARIANTS.md) and
  [GOVERNANCE.md](GOVERNANCE.md).
- **Knos 0.3.15**: no program changed. Clients, workflows, the site, documents and tests only;
  [CHANGELOG.md](../../CHANGELOG.md) has the list. The offer of a paid [Pilot](PILOT.md) and the page on who builds
  Knos ([TEAM.md](TEAM.md)) were written for it.
- **Knos 0.3.16 to 0.3.26** (5 to 10 Oct 2026): [CHANGELOG.md](../../CHANGELOG.md) has each list.

The story in short: we measured how often an agent's pull request said "tests pass" while a check had failed
(17.8% of repositories, on the first such pull request; 9 of 241 merged ones had a failed test, build, lint or type
check).

We then tried several products around that fact between 29 Sep and 2 Oct 2026, and kept the one that fixes it.

The commit history shows those turns.

`git log` and [CHANGELOG.md](../../CHANGELOG.md) are the dated record.

## Ideas and code from elsewhere

- **MergePay** ([github.com/codeswithroh/mergepay](https://github.com/codeswithroh/mergepay), first commit 23 Sep
  2026, on Arc mainnet since 24 Sep 2026) verifies GitHub's OIDC signature on an EVM chain, pays a GitHub user id,
  and links a wallet with a `workflow_dispatch` token from a repository the user owns. It did this before Knos.
  Knos first verified GitHub's signature on Solana in commit `cb3a1ac` (1 Oct 2026, Knos 0.3.7). We read MergePay
  on 2 Oct 2026. What we built after that follows or matches its design in these places: paying a GitHub id;
  binding a wallet with a token from a run in the user's own repository; holding an unbound payee's money for 180
  days and then returning it to the funder; reserving an issue by comment for 7 days; paying a person when a bot
  account opened the pull request; and a waiting time before a new signing key is active. No code was copied; the
  programs here are written for Solana from scratch.
- **Three pull requests by another GitHub account.** `jaystay-bot` wrote pull requests #32, #33 and #34 for
  bounties Knos funded on this repository on 2 Oct 2026: what `knos_bounties` says about each bounty, a
  repository's own record on the site, and a Ruby runner for the judge. That code is in the tree from 0.3.12, in
  commits under that account's name. The three were merged on 3 Oct 2026 and paid 48.75 test USDC in all.
- **Squads v4** is the multisig program that holds the second deployment's upgrade authority and its guardian
  role.
- **Shank** (Metaplex) is the format of the IDL files in `idl/`; they were written by hand from the programs'
  source, not generated.
- **Wycheproof** test vectors (Google, Apache-2.0) are in `programs/knos_oidc/tests/vectors/`, unmodified.
- **Sibyl** (`sibyl-memory-client`, by Sibyl Labs) is the memory engine, used as a dependency.
- Dependencies: `solana-program`, `solana-security-txt` (Rust); `typer`, `rich`, `solders` (Python). The web app
  loads `@wallet-standard/app` from a CDN only when a sponsor connects a wallet.
- The history and economics in [WHY.md](WHY.md) (the UCP 600, Akerlof, Spence, Holmström and Milgrom, and the
  studies cited there) are an argument, not a claim of endorsement.

## How the code is written

Commits in this repository were written with coding agents. Every commit is authored and reviewed by drexthealpha,
who is responsible for it. Commits carry no co-author trailers, because the author of record is the person who
reviewed and committed the change.

## Outstanding limits

Each limit is said once, on one line. No code can fix the first fourteen limits below: they need people, agreements or time. `python scripts/release_manifest.py`
copies these lines into [MANIFEST.md](MANIFEST.md).

- **No buyer has been interviewed.** Every statement here about what a buyer wants is reasoning from public sources.
- **No letter of intent.** Nobody has written that they would use or buy Knos.
- **No paying customer.** No price in the price book has been charged to anyone.
- **No pilot.** The [Pilot](PILOT.md) is an offer; nobody has bought it or been offered it.
- **No outside funder.** Knos's own account funded every task, in test money. Since 0.3.11, 3 payments have gone to another GitHub account, for three pull requests it wrote.
- **Outside key holders today: 0.** Both multisigs are 2-of-3 and one person holds all three keys ([KEYHOLDER.md](KEYHOLDER.md) says what changes it).
- **One founder, pseudonymous:** the GitHub account drexthealpha; no legal name is published.
- **No co-founder,** employee or adviser ([TEAM.md](TEAM.md)).
- **No legal entity.** Nothing can sign a contract, send an invoice or be sued as Knos, and there are no terms of service.
- **No legal advice taken.** [REGULATION.md](REGULATION.md) is what the founder read.
- **No outside review,** of the programs, the workflows, the relay, the clients, the site or the documents ([ASSURANCE.md](ASSURANCE.md)).
- **No shadow count.** The meter has never run beside anyone's invoices but Knos's own examples.
- **No outside program is known to read the verifier.** The interface and the examples are Knos's own ([COMPOSE.md](COMPOSE.md)).
- **No independent reproduction.** Nobody outside Knos has reported rebuilding the programs to the deployed hash, rerunning the benchmarks or running the drills.
- **No mainnet deployment.** Solana devnet and test USDC only; no real money has moved.
- **No second operator.** If the founder is unavailable, nobody answers a report, approves a key or cancels a proposal ([OPERATOR.md](OPERATOR.md)).
- **No organisation account.** The pinned workflows and the relay live in one personal GitHub account ([GOVERNANCE.md](GOVERNANCE.md), section 9).
- **The first deployment cannot be changed,** so its known limits stay ([SECURITY.md](SECURITY.md)); the second changes only through a multisig with a public 8-day delay.
