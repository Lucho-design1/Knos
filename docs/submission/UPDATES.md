# Knos: what changed during the hackathon

Every commit on `main` since the Submission Period opened (2026-09-30), by day, from `git log` (`scripts/submission_log.py`). Each line links its commit.

179 commits over 19 days.

## 2026-10-01 (59)

- [`ab7e0b3`](https://github.com/drexthealpha/Knos/commit/ab7e0b3) Knos 0.3.1: the work network for AI agents
- [`ed0b2ea`](https://github.com/drexthealpha/Knos/commit/ed0b2ea) Knos 0.3.2: passkey wallet on Tempo, recall 96.8%, real model workers
- [`2a2a160`](https://github.com/drexthealpha/Knos/commit/2a2a160) x402 on Solana built in with solders; agentpay no longer pins solders<0.28
- [`052d689`](https://github.com/drexthealpha/Knos/commit/052d689) Knos 0.3.3: installs everywhere, Sibyl Pro with every payment, recall wired, Tempo jobs in knos work, chain-direct web app, dead code removed
- [`b4d3e1a`](https://github.com/drexthealpha/Knos/commit/b4d3e1a) Read-all pass: fix x402-free sweep, Tempo key send, mirror records, CI chain markers; team claims from knos claim/MCP; stale text and dead code removed
- [`9630bf1`](https://github.com/drexthealpha/Knos/commit/9630bf1) rpc.wait: report a failed transaction only at the awaited commitment (a lost claim then sees its winner); fixes the team race the chain job caught
- [`f160013`](https://github.com/drexthealpha/Knos/commit/f160013) Knos 0.3.4: AI agent work counts only when Knos proves it
- [`78fe409`](https://github.com/drexthealpha/Knos/commit/78fe409) The release replay is test code: move it under tests; drop the unused pre-0.3.4 Moderato constants
- [`7ecf3dd`](https://github.com/drexthealpha/Knos/commit/7ecf3dd) CI under 5 minutes: uv with a cache, pytest -n auto, pinned and cached Solana CLI, 10 property rounds on PRs (200 nightly), mac and windows on 3.12 only on PRs (full matrix nightly), cancel superseded runs
- [`6885ddd`](https://github.com/drexthealpha/Knos/commit/6885ddd) 0.3.5: one pitch everywhere: AI agent work gets paid only when someone other than the agent proves it
- [`60956a8`](https://github.com/drexthealpha/Knos/commit/60956a8) Merge branch 'worktree-agent-a03f41911a8b5a49d' into release/0.3.5
- [`788c1ab`](https://github.com/drexthealpha/Knos/commit/788c1ab) Wired verifier: jobs post --verify names a verifier; knos verify re-runs the brief's checks and the buyer's recalled preferences, commits the evidence root, and pays or refunds on chain
- [`f1909da`](https://github.com/drexthealpha/Knos/commit/f1909da) Merge branch 'worktree-agent-a9826a8fa2cae8ecf' into release/0.3.5
- [`e7a89ee`](https://github.com/drexthealpha/Knos/commit/e7a89ee) Always-on worker and verifier in public Actions every 5 minutes (relay found from the devnet pointer); Windows CI in two shards; the reference verifier key
- [`a46016a`](https://github.com/drexthealpha/Knos/commit/a46016a) 0.3.5: COMPARE against marketplaces, agent protocols and coding agents; per-job margin in PRICING; CHANGELOG with what is next; the always-on worker runs by hand until its key secrets are set
- [`14436ca`](https://github.com/drexthealpha/Knos/commit/14436ca) Tests read the new pitch; the verify command is called by typer
- [`877ee70`](https://github.com/drexthealpha/Knos/commit/877ee70) Escrow 0.3.5: verifier-only verdicts (verify_reject), deadline settle crank, no self-claim, claim stake with timeout, settled jobs close and return rent to the buyer
- [`4b8cd65`](https://github.com/drexthealpha/Knos/commit/4b8cd65) program.yml: build, test and fuzz the escrow in Actions; upgrade devnet from main; 0.3.6
- [`4eff9ec`](https://github.com/drexthealpha/Knos/commit/4eff9ec) LowerFee: the admin can lower the fee, never raise it; the fee goes to max(2.5%, 0.05 USDC)
- [`9e3c811`](https://github.com/drexthealpha/Knos/commit/9e3c811) ERC-8183 job interface on the Tempo escrow: evaluator never the provider, only the evaluator or expiry settles a funded job, claimRefund unblockable, fee only on Completed; docs/ERC8183.md maps Knos to it
- [`f71f524`](https://github.com/drexthealpha/Knos/commit/f71f524) Attack tests read the vault after delivery returns the stake; knos jobs settle (the deadline crank); the always-on worker runs every 5 minutes and settles jobs past their deadline
- [`baece51`](https://github.com/drexthealpha/Knos/commit/baece51) The fee is max(2.5%, 0.05 USDC) everywhere: docs, help, Actions and the web app
- [`84ecb1c`](https://github.com/drexthealpha/Knos/commit/84ecb1c) The fuzz model reads the fee from the escrow's own config
- [`1b61fe9`](https://github.com/drexthealpha/Knos/commit/1b61fe9) The 0.3.6 escrow program, built in Actions (program.yml run 36900607431)
- [`cc6b0de`](https://github.com/drexthealpha/Knos/commit/cc6b0de) vulture: the stake rule, a settled job's state and the harness helper are used outside src
- [`20f847c`](https://github.com/drexthealpha/Knos/commit/20f847c) Escrow IDL (Anchor 0.1 format, one-byte tags), the unpublished @knos/escrow npm builders checked byte for byte against the Python builders, and a CPI example: an on-chain agent that claims and delivers
- [`6b15c95`](https://github.com/drexthealpha/Knos/commit/6b15c95) KnosEscrow 0.3.6 on Tempo Moderato (0x8B913C5946a4C1CD95089D7a563dB864d46b694E, fee max(2.5%, 0.05 USDC)): ABI and bytecode with the ERC-8183 jobs; deploys stay under the 30M per-transaction gas cap; the Foundry check expects 13 tests
- [`3afbc9a`](https://github.com/drexthealpha/Knos/commit/3afbc9a) Merge branch 'work' into release/0.3.6
- [`4b08e19`](https://github.com/drexthealpha/Knos/commit/4b08e19) Merge branch 'worktree-agent-ad6ff0e6c41324752' into release/0.3.6
- [`cb4a30c`](https://github.com/drexthealpha/Knos/commit/cb4a30c) LowerFee in the IDL; the web app and the Tempo client use the ERC-8183 contract (2.5% fee); 0.3.6 CHANGELOG
- [`8d2c399`](https://github.com/drexthealpha/Knos/commit/8d2c399) program.yml: the upgrade key is the Solana CLI's default signer for every devnet call
- [`9a5fc7b`](https://github.com/drexthealpha/Knos/commit/9a5fc7b) A verified job's delivery is one envelope: a copy sealed to the buyer and one to the verifier, both checked against the committed digest; program.yml keeps its key until the last devnet call
- [`ef62bbb`](https://github.com/drexthealpha/Knos/commit/ef62bbb) RPC calls back off on 429 (public devnet rate limits shared Actions runners); CHANGELOG for ERC-8183, the IDL and the envelope
- [`ee48291`](https://github.com/drexthealpha/Knos/commit/ee48291) COMPARE: every Knos cell measured on devnet in the 0.3.6 run, with the Knos win per row; CHANGELOG measurements
- [`1c32390`](https://github.com/drexthealpha/Knos/commit/1c32390) Always on without GitHub's cron: each worker run polls every 10 s for 4.5 minutes, then starts the next; the 5-minute schedule restarts the chain if it ever stops
- [`31da96d`](https://github.com/drexthealpha/Knos/commit/31da96d) 0.3.7: AI agent work gets paid only when GitHub's own signature, checked by Solana, proves it passed; sourced why-now figures
- [`cb3a1ac`](https://github.com/drexthealpha/Knos/commit/cb3a1ac) Escrow 0.3.7: GitHub Actions OIDC proof verified on chain (RSA-2048 Montgomery, tags 15-19)
- [`5e155ab`](https://github.com/drexthealpha/Knos/commit/5e155ab) Zero-install front door: paste an agent PR and see in seconds whether its tests-pass claim is true by GitHub's CI at the head commit; Protect this repo in two clicks; the Agent PR Index rebuilt every 30 minutes with its Merkle root attested on devnet
- [`2c4838a`](https://github.com/drexthealpha/Knos/commit/2c4838a) prove.yml: a reusable workflow that pays a GitHub-posted job on its Actions OIDC proof; knos prove --job --jwt-file pre-checks the token; knos proof run runs every [[check]]
- [`dd703a8`](https://github.com/drexthealpha/Knos/commit/dd703a8) Sibyl on the money path: a PR is checked against the repo's CONTRIBUTING.md rules (parsed once, then recalled from Sibyl) and the rules past rejections taught, before any check runs or anything is attested; each violation cites the rule's line and the PR's; a flagged PR becomes a required rule:<id>
- [`2fe3a9e`](https://github.com/drexthealpha/Knos/commit/2fe3a9e) Merge branch 'worktree-agent-a6ca8fb7f90064b5f' into release/0.3.7
- [`3d24706`](https://github.com/drexthealpha/Knos/commit/3d24706) Merge branch 'worktree-agent-ae0cbdafbe196e2c8' into release/0.3.7
- [`4ace74b`](https://github.com/drexthealpha/Knos/commit/4ace74b) 0.3.7 escrow: devnet faucet (20, 21), mint registry with a vault per mint (22), bounties that may be 0 (23); jobs in a registered mint store the mint
- [`2f9f268`](https://github.com/drexthealpha/Knos/commit/2f9f268) Front door reads the PR and its CI in parallel (refs/pull/N/head), re-reading at the PR's SHA if it moved; failing check names listed once
- [`1462d66`](https://github.com/drexthealpha/Knos/commit/1462d66) Bounty tests: fund the buyer and worker in the fixture (each xdist worker builds its own)
- [`b301efd`](https://github.com/drexthealpha/Knos/commit/b301efd) Merge branch 'worktree-agent-aec89c3171a4e0945' into release/0.3.7
- [`98b8082`](https://github.com/drexthealpha/Knos/commit/98b8082) knos_escrow.so 0.3.7 from Actions run 36916822061 (sha256 401b2d7e...05bc): faucet, mint registry, bounties; 96 tests and the 10,000-step fuzz green
- [`b990157`](https://github.com/drexthealpha/Knos/commit/b990157) Merge branch 'worktree-agent-aaddbae32a398908a' into release/0.3.7
- [`39b5ec9`](https://github.com/drexthealpha/Knos/commit/39b5ec9) GitHub proof jobs from Python: sol builders, market.post_github / prove_github, LiteSVM tests, fuzz with github jobs, IDL tags 15-19
- [`eb9b443`](https://github.com/drexthealpha/Knos/commit/eb9b443) scripts/register_github_keys.py: register GitHub's JWKS keys with the escrow (admin, devnet after deploy)
- [`5e765d9`](https://github.com/drexthealpha/Knos/commit/5e765d9) POST /gas: 0.01 devnet SOL for a passkey wallet's gas key, opt-in (--gas-key), one per key per day, 5 per IP per hour
- [`4952fd5`](https://github.com/drexthealpha/Knos/commit/4952fd5) Merge release/0.3.7 (bounties, faucet, multi-mint) with the GitHub proof (tags 15-19)
- [`6bbc48f`](https://github.com/drexthealpha/Knos/commit/6bbc48f) Bounty view: a passkey wallet (web/wallet.js: WebAuthn-guarded gas key in IndexedDB, PRF when available), gas from POST /gas, test USDC from the faucet, Fund this issue (PostBounty); Playwright timing script with a virtual authenticator
- [`3266b3b`](https://github.com/drexthealpha/Knos/commit/3266b3b) knos_escrow.so 0.3.7 from Actions run 36917472861 (sha256 8a31cccf...2b2a): GitHub Actions OIDC proof verified on chain (VerifyStep1 1,148,681 CU, VerifyStep2 1,193,853 CU) with bounties, faucet, multi-mint; 10,000-step fuzz green
- [`601f4e5`](https://github.com/drexthealpha/Knos/commit/601f4e5) program.yml runs the /gas tests
- [`dca799e`](https://github.com/drexthealpha/Knos/commit/dca799e) Knos proves its own work: .knos/proof.toml and a demo caller of prove.yml@v0.3.7
- [`979facd`](https://github.com/drexthealpha/Knos/commit/979facd) Merge commit '601f4e5' into release/0.3.7
- [`bb10e89`](https://github.com/drexthealpha/Knos/commit/bb10e89) 0.3.7 CHANGELOG
- [`81d40cd`](https://github.com/drexthealpha/Knos/commit/81d40cd) vulture: the 0.3.7 builders and proof constants are used by tests, scripts and clients

## 2026-10-02 (45)

- [`103b51a`](https://github.com/drexthealpha/Knos/commit/103b51a) 0.3.8
- [`37b1dec`](https://github.com/drexthealpha/Knos/commit/37b1dec) escrow: mont_sqr for the RSA squarings, SetAdmin (27), SetFeeAccount (28), security.txt
- [`07e386e`](https://github.com/drexthealpha/Knos/commit/07e386e) Docs: DISCLOSURE, MARKET, SECURITY proof scope and offline Stop hook, COMPARE rows for GH Bounty and Octasol; uv.lock; pinned fixtures (tests/fixtures/SHA256SUMS)
- [`02f919b`](https://github.com/drexthealpha/Knos/commit/02f919b) Merge branch 'worktree-agent-aa0c27098150c700b' into release/0.3.8
- [`42a2d68`](https://github.com/drexthealpha/Knos/commit/42a2d68) 0.3.8 ops: Squads time-locked authority scripts, verified build deploy, cargo-audit, knos mainnet-check
- [`abb5535`](https://github.com/drexthealpha/Knos/commit/abb5535) escrow: SetWorkflow (24): a proof's job_workflow_sha must be in the registry; the tag-prefix check is gone
- [`6184c00`](https://github.com/drexthealpha/Knos/commit/6184c00) 0.3.8 C: GitHub-native bounties with no secret in the repo: fund.yml, relay.yml, caller workflow, worker relay, PR receipt line
- [`0a6e01e`](https://github.com/drexthealpha/Knos/commit/0a6e01e) knos_escrow.so: the build from program.yml run 36950967722
- [`c386e4a`](https://github.com/drexthealpha/Knos/commit/c386e4a) devnet Squads multisig 2-of-3, 300 s time lock; mainnet-check defaults to it
- [`54bcb2a`](https://github.com/drexthealpha/Knos/commit/54bcb2a) One product: claims, budgets, Pro, Tempo, text jobs and the relay move under knos labs; all code MIT; modelled benchmarks removed
- [`8b0dd89`](https://github.com/drexthealpha/Knos/commit/8b0dd89) 0.3.8 F: Sibyl load-bearing - tamper learned per repo and agent; knos memory export/import/note
- [`72b4f8e`](https://github.com/drexthealpha/Knos/commit/72b4f8e) Merge branch 'worktree-agent-a895b15416761fdf4' into release/0.3.8
- [`8572788`](https://github.com/drexthealpha/Knos/commit/8572788) Merge branch 'worktree-agent-a8b4f0723d9072a5d' into release/0.3.8
- [`b142ea8`](https://github.com/drexthealpha/Knos/commit/b142ea8) program.yml: solana-verify build needs an absolute mount path
- [`e8181cb`](https://github.com/drexthealpha/Knos/commit/e8181cb) Merge branch 'worktree-agent-aa2b1c972d81754b0' into release/0.3.8
- [`c6ff343`](https://github.com/drexthealpha/Knos/commit/c6ff343) 0.3.8 A: prove.yml judges PRs against held-out acceptance tests (overlay, protected paths, sentinel, fail-to-pass), 5-part OIDC audience, tamper benchmark
- [`08b68ea`](https://github.com/drexthealpha/Knos/commit/08b68ea) escrow: 5-part proof audience (job, head sha, checks hash, payout), checks hash and stake_required fixed at PostGithub, permissionless relay
- [`2742aae`](https://github.com/drexthealpha/Knos/commit/2742aae) Merge branch 'worktree-agent-a5c69dd58e8fd161a' into release/0.3.8
- [`69e33ac`](https://github.com/drexthealpha/Knos/commit/69e33ac) deadcode: the always-on worker's relay is an entry point
- [`ff3c380`](https://github.com/drexthealpha/Knos/commit/ff3c380) Merge commit 'b142ea81d4e1608037dad5addb717e9c2895b25b' into release/0.3.8
- [`6730fa6`](https://github.com/drexthealpha/Knos/commit/6730fa6) knos_escrow.so from program.yml run 36952149071; prove pre-check tests: sha pin and 5-part audience
- [`ba32d70`](https://github.com/drexthealpha/Knos/commit/ba32d70) knos help memory fits 80 columns
- [`9ec5a6b`](https://github.com/drexthealpha/Knos/commit/9ec5a6b) Merge commit '6730fa651b12a9f3a726733276a1c6e59a24223a' into release/0.3.8
- [`c991a90`](https://github.com/drexthealpha/Knos/commit/c991a90) Merge branch 'worktree-agent-a895b15416761fdf4' into release/0.3.8
- [`c49b54f`](https://github.com/drexthealpha/Knos/commit/c49b54f) The tamper bench's sample is data, not part of the suite; help for mainnet-check; vulture for the hand-over builders
- [`b324367`](https://github.com/drexthealpha/Knos/commit/b324367) mainnet-check help fits 80 columns
- [`2434577`](https://github.com/drexthealpha/Knos/commit/2434577) The tamper benchmark runs where prove.yml's judge runs (Linux, Windows); skipped on macOS with the reason
- [`67bc0a2`](https://github.com/drexthealpha/Knos/commit/67bc0a2) Skip the whole tamper benchmark module on macOS, with the reason
- [`c2ee845`](https://github.com/drexthealpha/Knos/commit/c2ee845) verified-build: pin solana-verifiable-build 2.3.11 (rustc 1.84) for build and verify-from-repo
- [`12a11bc`](https://github.com/drexthealpha/Knos/commit/12a11bc) Agent PR Index: 2,000+ PR scan, Wilson intervals, self-repo exclusion, distinct-funder proofs
- [`f3414b3`](https://github.com/drexthealpha/Knos/commit/f3414b3) relay: a refused pull request gets the judge's reasons; a paid proof gets a SAS receipt; relay.yml pinned on its own
- [`04f7e58`](https://github.com/drexthealpha/Knos/commit/04f7e58) prove.yml: the judge runs the repo's CONTRIBUTING rules first and learns what it refused (kept in the caller's Actions cache); knos-ref installs knos from the pinned Knos commit
- [`aa5cd7f`](https://github.com/drexthealpha/Knos/commit/aa5cd7f) Merge remote-tracking branch 'origin/c2-e2e' into merge-c2
- [`c77f40a`](https://github.com/drexthealpha/Knos/commit/c77f40a) Stop hook: a paid PR's body links the receipt the relay attested for the payment
- [`dd8ff57`](https://github.com/drexthealpha/Knos/commit/dd8ff57) Agent PR Index ships as a release asset: 2,431 PRs with finished CI, attested in the Pages build
- [`ce49c91`](https://github.com/drexthealpha/Knos/commit/ce49c91) Squads handover: real SetAdmin layout (tag / new_admin[32]); approve/execute script; mainnet-check reads the CI verified build on devnet
- [`6c76e77`](https://github.com/drexthealpha/Knos/commit/6c76e77) Merge remote-tracking branch 'origin/i4-index' into merge-i4
- [`b8281fa`](https://github.com/drexthealpha/Knos/commit/b8281fa) knos-escrow 0.3.9: issuer registry (25, GitHub + GitLab CI keys scoped per issuer), FundWithToken (26, devnet: a fund.yml token funds a github job with minted test USDC, one per repo per hour), the version in the binary (29) and a client that refuses a mismatch
- [`de53c28`](https://github.com/drexthealpha/Knos/commit/de53c28) Merge remote-tracking branch 'origin/main' into p1
- [`635989b`](https://github.com/drexthealpha/Knos/commit/635989b) Merge remote-tracking branch 'origin/t3-trust' into merge-t3
- [`619c16e`](https://github.com/drexthealpha/Knos/commit/619c16e) Merge remote-tracking branch 'origin/c2-e2e' into merge-c2b
- [`d8ead42`](https://github.com/drexthealpha/Knos/commit/d8ead42) Merge remote-tracking branch 'origin/main' into p1
- [`50bf744`](https://github.com/drexthealpha/Knos/commit/50bf744) Knos 0.3.9: AI agent work gets paid only when GitHub's own signature, checked by Solana, proves it passed
- [`0e76b28`](https://github.com/drexthealpha/Knos/commit/0e76b28) Knos 0.3.10: one product. Agent work is paid on GitHub's signature, verified on Solana by programs nobody can change
- [`f3dfd3d`](https://github.com/drexthealpha/Knos/commit/f3dfd3d) Knos 0.3.11: a merge pays only when the pull request's claims hold, agents find paid work, others can build on it

## 2026-10-03 (4)

- [`53e4e39`](https://github.com/drexthealpha/Knos/commit/53e4e39) feat(mcp): knos_bounties says what each bounty is about (title, labels, assigned) (#32) (by jaystay-bot)
- [`b937a9f`](https://github.com/drexthealpha/Knos/commit/b937a9f) feat(site): the Check a PR box takes a repository and shows its record in the Agent PR Index (#33) (by jaystay-bot)
- [`8d0b4a4`](https://github.com/drexthealpha/Knos/commit/8d0b4a4) feat(judge): a ruby runner for bounties paid on tests (#34) (by jaystay-bot)
- [`3bf54a1`](https://github.com/drexthealpha/Knos/commit/3bf54a1) Knos 0.3.12: a second deployment that can be fixed, terms fixed at funding, paid to a wallet in the same minute

## 2026-10-04 (5)

- [`1ea0a53`](https://github.com/drexthealpha/Knos/commit/1ea0a53) Add cluster and overall fields to status JSON (#40) (by Xia San)
- [`1d83c3f`](https://github.com/drexthealpha/Knos/commit/1d83c3f) Document Knos checks in GitLab merge requests (#41) (by Xia San)
- [`e886acd`](https://github.com/drexthealpha/Knos/commit/e886acd) Show first deployment holds in site account lookup (#43) (by Xia San)
- [`567fd12`](https://github.com/drexthealpha/Knos/commit/567fd12) Knos 0.3.13: work orders that pay on signed acceptance, a seller who can settle without the buyer, and a business beyond one fee
- [`6eb81dd`](https://github.com/drexthealpha/Knos/commit/6eb81dd) Knos 0.3.14: every signed token is single-use, a neutral count that costs less than it charges, and work an agent can take and be paid for alone

## 2026-10-05 (1)

- [`72511b3`](https://github.com/drexthealpha/Knos/commit/72511b3) Knos 0.3.15: a console for whoever approves the invoice, billing by deliverable, and evidence that outlives devnet

## 2026-10-06 (2)

- [`50ecb05`](https://github.com/drexthealpha/Knos/commit/50ecb05) Knos 0.3.16: a first screen you can drive, an invoice checked with no install, and a stricter verifier
- [`f03ec51`](https://github.com/drexthealpha/Knos/commit/f03ec51) Knos 0.3.17: bring your own invoice; correct work is accepted; four verdicts, four ids, one ledger of events

## 2026-10-07 (2)

- [`f8bcd9d`](https://github.com/drexthealpha/Knos/commit/f8bcd9d) Knos 0.3.18: priced like a protocol, a kit for the supplier, a commitment that binds every event
- [`155b570`](https://github.com/drexthealpha/Knos/commit/155b570) Knos 0.3.19: what exists made true, fast and used

## 2026-10-08 (3)

- [`fb77f4f`](https://github.com/drexthealpha/Knos/commit/fb77f4f) Knos 0.3.20: one transaction, followed to its end
- [`042b7de`](https://github.com/drexthealpha/Knos/commit/042b7de) Knos 0.3.21: what exists made true, enforceable and usable by strangers
- [`c4350c9`](https://github.com/drexthealpha/Knos/commit/c4350c9) Knos 0.3.22: more relays, fewer stale words, memory that changes a decision

## 2026-10-09 (2)

- [`852e613`](https://github.com/drexthealpha/Knos/commit/852e613) Knos 0.3.23: four steps on every line, owed both ways
- [`fb4217c`](https://github.com/drexthealpha/Knos/commit/fb4217c) Knos 0.3.24: the lead number read again, assurance per line

## 2026-10-10 (2)

- [`095f52a`](https://github.com/drexthealpha/Knos/commit/095f52a) Knos 0.3.25: a ten-second check anyone can share; the twenty launch checks answered
- [`d72a7d3`](https://github.com/drexthealpha/Knos/commit/d72a7d3) Knos 0.3.26

## 2026-10-11 (2)

- [`79f19da`](https://github.com/drexthealpha/Knos/commit/79f19da) Knos 0.3.27
- [`99cc4e3`](https://github.com/drexthealpha/Knos/commit/99cc4e3) Knos 0.3.28

## 2026-10-14 (5)

- [`ee456a5`](https://github.com/drexthealpha/Knos/commit/ee456a5) Knos 0.3.29 branch: referee, outcomes, gate, record, money, agents, self, ZK, platform
- [`a4ea15c`](https://github.com/drexthealpha/Knos/commit/a4ea15c) Knos 0.3.30 branch: decided prices, one-transaction v3 GitHub check, Nemotron self-loop entry
- [`88eebd5`](https://github.com/drexthealpha/Knos/commit/88eebd5) Knos 0.3.31 branch: one repository, every no-key capability, built by using Knos as a customer
- [`a2ce54e`](https://github.com/drexthealpha/Knos/commit/a2ce54e) Knos 0.3.32 branch: final on Alpenglow, and Knos priced per verified merge for teams
- [`b838b98`](https://github.com/drexthealpha/Knos/commit/b838b98) Knos 0.3.33 branch: the demand check runs on Qloo's official MCP server

## 2026-10-15 (3)

- [`511fb84`](https://github.com/drexthealpha/Knos/commit/511fb84) Knos 0.3.34 branch: an idea from any field crosses the valley of death
- [`169cfc0`](https://github.com/drexthealpha/Knos/commit/169cfc0) Knos 0.3.34 branch: one repository
- [`cc7f540`](https://github.com/drexthealpha/Knos/commit/cc7f540) Knos 0.3.34 branch: CI green again

## 2026-10-16 (6)

- [`299858b`](https://github.com/drexthealpha/Knos/commit/299858b) Knos: is it wanted, before anyone's money is locked
- [`25bf972`](https://github.com/drexthealpha/Knos/commit/25bf972) Knos: landmark research in, a code-made demand decision out
- [`6032250`](https://github.com/drexthealpha/Knos/commit/6032250) Knos demand check: the money path works on the hosted service
- [`11b7d0c`](https://github.com/drexthealpha/Knos/commit/11b7d0c) Knos demand check: pre-orders fit a Solana transaction with room to spare
- [`2873293`](https://github.com/drexthealpha/Knos/commit/2873293) Knos crosses the valley of death with Qloo as its demand oracle
- [`67b45b3`](https://github.com/drexthealpha/Knos/commit/67b45b3) Knos demand check: the judge's four findings closed

## 2026-10-17 (4)

- [`53fe513`](https://github.com/drexthealpha/Knos/commit/53fe513) Knos: six roles on one page, the full stack where it acts
- [`ca31e8e`](https://github.com/drexthealpha/Knos/commit/ca31e8e) Knos: the contribute role works on a fresh server
- [`66be0a1`](https://github.com/drexthealpha/Knos/commit/66be0a1) Knos: CI green again, and contributors' work reaches the referee
- [`aa376e3`](https://github.com/drexthealpha/Knos/commit/aa376e3) Knos 0.4.0: anyone can take part in turning research into a product

## 2026-10-18 (4)

- [`eb12d1b`](https://github.com/drexthealpha/Knos/commit/eb12d1b) Knos: every flow is real, no stand-ins
- [`d00e6c2`](https://github.com/drexthealpha/Knos/commit/d00e6c2) Knos: the live faucet pays, the app opens in one tap, CI portable
- [`6635a75`](https://github.com/drexthealpha/Knos/commit/6635a75) Knos: milestone evidence must be a page that does not change
- [`17b8811`](https://github.com/drexthealpha/Knos/commit/17b8811) Knos: the site's link rule knows its own wake page

## 2026-10-19 (8)

- [`dfa021a`](https://github.com/drexthealpha/Knos/commit/dfa021a) Knos: back research products in one tap; everything real, no accounts
- [`fec7aa7`](https://github.com/drexthealpha/Knos/commit/fec7aa7) Knos: the front door ships today's products; the referee daemon rides out network errors
- [`37ac31a`](https://github.com/drexthealpha/Knos/commit/37ac31a) Knos: the network page reads 45 bytes, not whole programs
- [`82cd901`](https://github.com/drexthealpha/Knos/commit/82cd901) Knos: money locks only on a brief that is Ready to fund
- [`e35a143`](https://github.com/drexthealpha/Knos/commit/e35a143) Knos: a company's multisig from a passkey, track records, SSO on mocksaml
- [`d8a9a1d`](https://github.com/drexthealpha/Knos/commit/d8a9a1d) Knos: the home page's "Check a claim", and the brief check draws its latest answer
- [`b3c43ae`](https://github.com/drexthealpha/Knos/commit/b3c43ae) Knos: tests for track records and passkey multisigs, and Lighthouse on the live site
- [`a82e7ea`](https://github.com/drexthealpha/Knos/commit/a82e7ea) Knos: pending upgrades read from devnet after the first paint

## 2026-10-20 (6)

- [`fbc7d1a`](https://github.com/drexthealpha/Knos/commit/fbc7d1a) Knos: a clear brief costs half the reasoning, measured
- [`bc44c40`](https://github.com/drexthealpha/Knos/commit/bc44c40) Knos: track-record badges, a compressed log, live accounts and an app for everyone
- [`0e3f228`](https://github.com/drexthealpha/Knos/commit/0e3f228) Knos: each brief shows what it measured, and every passkey step shows its card first
- [`a4abd16`](https://github.com/drexthealpha/Knos/commit/a4abd16) Knos: a private pledge proven on devnet, a brief in one sentence, help beside every page
- [`d55186e`](https://github.com/drexthealpha/Knos/commit/d55186e) Knos: a second free devnet RPC, every decision in plain words, help that never covers a button
- [`71d74b9`](https://github.com/drexthealpha/Knos/commit/71d74b9) Knos: cursors never use up your limit, #network paints at once, finality stays on the card

## 2026-10-21 (16)

- [`165b635`](https://github.com/drexthealpha/Knos/commit/165b635) Knos: the app's header stays on one line; Lighthouse measures this commit, not the live app
- [`364db67`](https://github.com/drexthealpha/Knos/commit/364db67) Knos: every Qloo family on every interface, and Solana and Sibyl covered row by row
- [`ed6a9df`](https://github.com/drexthealpha/Knos/commit/ed6a9df) Knos: project credits move only into the escrow, on devnet
- [`a3cb05f`](https://github.com/drexthealpha/Knos/commit/a3cb05f) Knos: a launch area given as coordinates is searched there, and every brief keeps what was asked of Qloo
- [`7095fc9`](https://github.com/drexthealpha/Knos/commit/7095fc9) Knos: the price-tier heatmap is read for the area asked
- [`a7a5a6e`](https://github.com/drexthealpha/Knos/commit/a7a5a6e) Knos: one story everywhere: research across the valley of death, each step paid only on verified proof
- [`702900c`](https://github.com/drexthealpha/Knos/commit/702900c) Knos: a project can be taken off the public list; the live demand run goes into a locked brief
- [`6352e8a`](https://github.com/drexthealpha/Knos/commit/6352e8a) Knos: projects survive a redeploy, kept on devnet; malformed briefs get "Not ready", never a 500
- [`77aed35`](https://github.com/drexthealpha/Knos/commit/77aed35) Knos: every Qloo value links to its trace; Qloo with and without, measured; Qloo used safely
- [`6490760`](https://github.com/drexthealpha/Knos/commit/6490760) Knos: a live count of people outside Knos, an invite page, and the judge's first-verdict check
- [`ed6367a`](https://github.com/drexthealpha/Knos/commit/ed6367a) Knos: the first demand verdict asks Qloo's independent questions at once; decisions link their source
- [`389a3d8`](https://github.com/drexthealpha/Knos/commit/389a3d8) Knos: the verdict no longer waits on Qloo's heatmap
- [`b120bdb`](https://github.com/drexthealpha/Knos/commit/b120bdb) Knos: a report's independent parts ask Qloo at once
- [`d513cd5`](https://github.com/drexthealpha/Knos/commit/d513cd5) Knos: places, persona tags and launch cities join the report's concurrent parts
- [`2884b2d`](https://github.com/drexthealpha/Knos/commit/2884b2d) Knos: the tag questions go to Qloo with the first search
- [`807b17d`](https://github.com/drexthealpha/Knos/commit/807b17d) Knos: the hackathon submission, a fresh-container setup check, uptime from GitHub's record, and this goal's own tokens
