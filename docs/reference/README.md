<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Every document, under six questions

**In plain words.** This page lists every Knos document once, under six questions. The seven pages to read first are on [the front map](../README.md). When a word is new to you, look it up in [the word list](../WORDS.md).

```mermaid
flowchart TB
    you(["You have a question"])
    q1["1. Does it work? Start with STORY.md"]
    q2["2. Why does it matter? Start with WHY.md"]
    q3["3. What is new? Start with VERIFIER.md"]
    q4["4. How do I use it? Start with START.md"]
    q5["5. How do I build on it? Start with COMPOSE.md"]
    q6["6. How is it run and paid for? Start with PRICING.md"]
    you --> q1
    you --> q2
    you --> q3
    you --> q4
    you --> q5
    you --> q6
```
*Pick your question; each one has a first page to read.*

The documents in this folder are listed below, with the seven front pages too.

`tests/test_docs_map.py` fails when a file in this folder is missing from this page.

## 1. Does it work?

| document | what it answers |
|---|---|
| [STORY.md](../STORY.md) | one task in seven steps on one page, each with its evidence |
| [MANIFEST.md](MANIFEST.md) | this release on one page: source, the build live at each public id, every capability's stage, the limits |
| [CAPABILITIES.md](CAPABILITIES.md) | every capability, the stage it has reached, and the file or transaction that shows it |
| [BENCH.md](BENCH.md) | every measured number, with the command that reproduces it |
| [SLOP_AUDIT.md](SLOP_AUDIT.md) | how many AI agent pull requests in the public AIDev dataset would fail Knos's checks, measured |
| [TAMPER.md](TAMPER.md) | which cheating submissions each judge refuses, and how much correct work each accepts |
| [KNOS_RECORD.md](KNOS_RECORD.md) | every check, cheat caught and payout as one hash-chained public file, anchored on devnet, and how to verify it |
| [REFEREE_FROST.md](REFEREE_FROST.md) | the referee panel as one FROST key (2 of 3 hosts sign) and the code referee's attestation: knos_oidc on chain, Sigstore |
| [REFEREE.md](REFEREE.md) | the referee: Works (sealed tests, a locked judge, the cheat library, re-runs), Wanted and Makeable, and the free maintainer mode |
| [LOAD.md](LOAD.md) | many orders open at once, in the local simulator |
| [DRILLS.md](DRILLS.md) | the safety paths, tested on the same program files that run on devnet |
| [drills_recovery.md](drills_recovery.md) | what a funder does in three failures, with a key of their own |
| [INVARIANTS.md](INVARIANTS.md) | what holds about money and concurrency, each with its test |
| [ASSURANCE.md](ASSURANCE.md) | the tests, the fuzzing and the proofs; no outside firm has reviewed anything |
| [UNWRAPS.md](UNWRAPS.md) | every place a program can panic, and why it cannot be reached |
| [PROVENANCE.md](PROVENANCE.md) | how each deployed program traces back to the source code it was built from |
| [FAUCET.md](FAUCET.md) | how a stranger gets test USDC and funds a first task, the faucet's rules, and its key |
| [REPRODUCE.md](REPRODUCE.md) | how someone else runs it and files a signed report |
| [REPRODUCED.md](REPRODUCED.md) | knos.yml: a research repository's claims re-run on a second machine and held-out data; contested results stay private |
| [OPERATIONS.md](OPERATIONS.md) | whether the canary and the relay are working, from the public record |
| [KEEPALIVE.md](KEEPALIVE.md) | keeping the app awake: every worker chain run pings it, the watchdog revives the chain, the PC daemon pings too |
| [NUMBERS.md](../NUMBERS.md) | nine numbers about use by anyone outside, zeros included |
| [TRANSACTION.md](../TRANSACTION.md) | one order told end to end for a finance reader: terms, a rejection, an acceptance, payment, a refused replay |
| [FLOWS.md](FLOWS.md) | three things to try, in order: check one pull request, follow one paid task, two copies give one bill |

## 2. Why does it matter?

| document | what it answers |
|---|---|
| [WHY.md](WHY.md) | why a signed run and not a description |
| [VENDORS.md](VENDORS.md) | a page per rated agent vendor: its numbers, its right of reply, and how to earn the badge |
| [INDEX.md](INDEX.md) | the Agent PR Index: how often "tests pass" agrees with the checks, by agent and week |
| [INDEX_METHOD.md](../INDEX_METHOD.md) | the frozen count method, version 1, and a draft version 2 that also re-checks the pull requests counted as clean |
| [MARKET.md](MARKET.md) | the price book, and what is devnet only or not yet legal |
| [PILOT.md](PILOT.md) | the one offer for money, and the fair test written before it starts |
| [SHADOW.md](SHADOW.md) | a neutral count beside an invoice a buyer already receives |
| [SHARE.md](SHARE.md) | share a check: link, copied result, X post box, PNG card, README badge |

## 3. What is new?

| document | what it answers |
|---|---|
| [VERIFIER.md](VERIFIER.md) | a Solana program that checks the signed identity tokens of GitHub, GitLab, Google and others |
| [OIDC.md](OIDC.md) | the `knos-oidc` program, instruction by instruction |
| [METER.md](METER.md) | what is counted, the two ledgers, and the statement both sides rebuild |
| [EVENTS.md](EVENTS.md) | one log of events under every recording mode: ids, acknowledgements, corrections, duplicates |
| [RECEIPT.md](RECEIPT.md) | the acceptance receipt and its schema |
| [TERMS.md](TERMS.md) | terms a contract can cite by hash |
| [DISPUTES.md](DISPUTES.md) | who can do what in a dispute, at each state, with nobody from Knos |
| [LIABILITY.md](LIABILITY.md) | each way the count can be wrong, what the software does, and what nobody has signed for |
| [OUTCOMES.md](OUTCOMES.md) | outcomes other than a merged pull request |
| [MEASURED.md](MEASURED.md) | pay for a result measured from data: a control group by hash, tiers under a cap |
| [X402.md](X402.md) | a proposal: pay on signed acceptance over x402, open upstream as a draft pull request |

## 4. How do I use it?

| document | what it answers |
|---|---|
| [START.md](../START.md) | get started in five minutes: check a pull request, fund a task, get paid, install the command |
| [WORDS.md](../WORDS.md) | every technical word in one plain line |
| [INSTALL.md](INSTALL.md) | every way to install the command, the check and the workflows |
| [PLAYGROUND.md](PLAYGROUND.md) | fund a test order with one comment, with a GitHub account and nothing else |
| [CONSOLE.md](CONSOLE.md) | the console, for whoever authorises a payment |
| [FINANCE.md](FINANCE.md) | the four records of a deliverable, and the accounting exports |
| [RAILS.md](RAILS.md) | paying by bank: evidence, statement, approval, a payment instruction file, and the status coming back |
| [NETTING.md](NETTING.md) | small outcomes netted into one release per supplier per period, and what the chain enforces of it |
| [SUPPLIER.md](SUPPLIER.md) | for the supplier: the rules before the work, every refusal in plain words, appeals |
| [PAYEE.md](PAYEE.md) | the payout page: a passkey address, one link, the run you start; why it is not one click |
| [RECORD.md](RECORD.md) | the supplier's kit: a public record, a badge, one line to install, a receipt for the invoice |
| [ADVANCE.md](ADVANCE.md) | an advance by a third party against a funded order: the offer, the one transaction, the three ends, no recourse |
| [RETENTION.md](RETENTION.md) | what a root proves and does not, who keeps what, and what still verifies if Knos is gone |
| [VAULT.md](VAULT.md) | keeping evidence: sealed bundles, export, retention, checkpoints, a restore drill |
| [PRIVATE.md](PRIVATE.md) | a neutral count for private repositories without showing the code |
| [BUYER.md](BUYER.md) | post a task as a buyer: spec, sealed hidden tests, the funding command and its fee |
| [AGENTS.md](AGENTS.md) | an agent finds work, takes it, submits it and is paid |
| [HERMES.md](HERMES.md) | Knos in Hermes Agent: the skill, the MCP server (stdio and HTTP), the plugin, the referee as GEPA's judge, an Atropos environment |
| [AUTORESEARCH.md](AUTORESEARCH.md) | autoresearch for anyone: agents change one file, the referee keeps or refuses each run, sealed data decides payment |
| [GAME.md](GAME.md) | the Knos game: people and AI scientists attack one sealed goal at once; a pooled pot split by the referee's verdicts |
| [DEMAND_CHECK.md](DEMAND_CHECK.md) | the demand check on Qloo's MCP server: a maker's demand report, a buyer agent, pre-orders held on devnet |
| [REFUSE.md](REFUSE.md) | what Knos will not fund: the refuse list every Ready check applies |
| [MCP_STORE.md](MCP_STORE.md) | Knos in AI assistants: the read-only app-store MCP, its tools, limits and privacy |
| [OUTSIDE_TRUTH.md](OUTSIDE_TRUTH.md) | Open signals scored against 200 past SBIR awards with known outcomes: no better than chance |
| [QLOO-COVERAGE.md](QLOO-COVERAGE.md) | every Qloo parameter, type and endpoint the docs list, and where a person sets it on each interface |
| [IDEAS.md](IDEAS.md) | an idea in from anyone or any research source, every field; demand, then pull commitments released in stages |
| [NEBIUS.md](NEBIUS.md) | Nemotron models on Nebius Token Factory as Knos coders and cheat explainers, Tavily provenance; the referee still decides |
| [LABS.md](LABS.md) | cloud labs and fabs through one interface: the lab paid on protocol and QC, the researcher on the outcome |
| [TEAMS.md](TEAMS.md) | Knos for teams: per verified merge, per agent check, bounty fee, task packages; metering, chain-checked invoices, the dashboard |

## 5. How do I build on it?

| document | what it answers |
|---|---|
| [COMPOSE.md](COMPOSE.md) | the verifier, the payment program and the record, from another program |
| [GATE.md](GATE.md) | the upgrade gate for your own program: three commands, and what it cannot do |
| [PR_GATE.md](PR_GATE.md) | Knos Gate: sealed hidden tests and cheat checks on outside pull requests, one check, one comment, a signed receipt |
| [CODE_SCANNING.md](CODE_SCANNING.md) | Gate's findings as code-scanning alerts and line annotations, an attested receipt, and a required check |
| [MCP_SERVER.md](MCP_SERVER.md) | knos mcp's resources, prompts, output schema, tasks and skills, and the person's confirmation before each post |
| [TOKEN_SAFETY.md](TOKEN_SAFETY.md) | Token-2022 extensions that would break held money or a payout, and the check that refuses them |
| [PRIORITY_FEES.md](PRIORITY_FEES.md) | priority fees on a limit sized by simulation, and a WebSocket wait for confirmation |
| [SELF.md](SELF.md) | Knos builds Knos: agents improve product code, judged by the referee from main, paid on devnet |
| [ES256.md](ES256.md) | a second kind of signed token (ES256), checked in one transaction; live on devnet since 9 Oct 2026 |
| [ALPENGLOW.md](ALPENGLOW.md) | how Knos tells a cluster runs Alpenglow, waits until a payment is final there, and how long that took on devnet |
| [SOLANA-COVERAGE.md](SOLANA-COVERAGE.md) | every Solana devnet RPC method, Token-2022 extension, program, payment path and upgrade, used or not and why |
| [PLATFORM.md](PLATFORM.md) | the programs on today's Solana: sBPF v3 builds, a GitHub token verified in one transaction, v1 transactions, finality, and the upgrade steps |
| [PAY_ON_PROOF.md](PAY_ON_PROOF.md) | pay on proof: m of n referee signatures, ORCID iDs as payees, and a container-image judge path that has never run |
| [CONFORMANCE.md](CONFORMANCE.md) | the formats, with test vectors and a runner |
| [INTEGRATIONS.md](INTEGRATIONS.md) | what a bounty or work platform can take; no platform uses it |
| [ADAPTERS.md](ADAPTERS.md) | other systems' events, and what the chain can check of them |
| [RELAY.md](RELAY.md) | the relay: anyone can run one |
| [SOURCES.md](SOURCES.md) | signed results from systems other than CI: which can be neutral evidence |
| [TASK_PACKAGES.md](TASK_PACKAGES.md) | a merged issue and fix as a sealed, verified task; maintainer opt-in; grading with cheat rules |
| [ZK.md](ZK.md) | a research score proven without showing the hidden test set: Groth16 checked on Solana; toy setup |
| [DURABLE_NONCES.md](DURABLE_NONCES.md) | the measured blockhash life, and held money funding signed now and sent later by another party |
| [X402_UPTO.md](X402_UPTO.md) | x402 `upto` on Solana: one ceiling held, the checks used charged, the rest refunded, on devnet |
| [SAS_INPUTS.md](SAS_INPUTS.md) | attestations by issuers an order trusts, read as conditions before money moves |
| [SPENDING_LIMITS.md](SPENDING_LIMITS.md) | Squads spending limits for bounded treasury costs, run on a test multisig, and the founder's steps |
| [KORA_CCTP.md](KORA_CCTP.md) | gasless sends through a Kora fee relayer, and USDC from EVM chains into held money by CCTP V2 |
| [A2A.md](A2A.md) | Knos as an A2A agent: its Agent Card and the skills other agents can call |
| [CLAUDE_AGENTS.md](CLAUDE_AGENTS.md) | Claude agents as guarded attempts, Knos judging Managed Agents, structured outputs and prompt caching |

## 6. How is it run and paid for?

| document | what it answers |
|---|---|
| [PRICING.md](../PRICING.md) | what it costs: the check is free, the fee on a paid task, the meter's price |
| [TRUST.md](../TRUST.md) | who holds the keys today, what is tested and proven, and how to check a program yourself |
| [GOVERNANCE.md](GOVERNANCE.md) | who can change what today, and three plans that are not done |
| [MONEY.md](MONEY.md) | the one fee config, graduation held money and pre-orders, contributor splits, x402, the revenue data |
| [CHARTER.md](CHARTER.md) | the rights Knos gives you: each enforced by a named test, or marked a promise |
| [STANDARD.md](STANDARD.md) | how work should be judged and rule-breakers treated: what runs today, what is only a plan |
| [KEYS.md](KEYS.md) | who holds the keys today, and the plan |
| [PROPOSAL-2.3.md](PROPOSAL-2.3.md) | the proposed knos_pay 2.3 upgrade, in plain words |
| [KEYHOLDER.md](KEYHOLDER.md) | hold a member key: what it can do, and three steps to ask; outside holders today: 0 |
| [SELFHOST.md](SELFHOST.md) | the record API, relay and approver in your cloud; single sign-on through any OpenID Connect provider, tested against a stand-in provider only |
| [OPERATOR.md](OPERATOR.md) | a second person runs it from a clean machine; the drill nobody has run yet |
| [TEAM.md](TEAM.md) | who builds it today, and what an outside key holder would do |
| [SECURITY.md](SECURITY.md) | who is trusted for what, every command and term, and every limit |
| [ATTESTOR.md](ATTESTOR.md) | what the forge's signature proves and does not, and five ways to narrow the gap; two exist |
| [MAINNET.md](MAINNET.md) | the gates between devnet and mainnet; not planned for this release |
| [BOUNDARY.md](BOUNDARY.md) | where enterprise funds live, and which program enforces each spending limit and approval |
| [ENFORCEMENT.md](ENFORCEMENT.md) | each route that can spend, against each restriction: enforced by the program, by the workflow, advisory, or outside |
| [CONTROLS.md](CONTROLS.md) | for a security or procurement review: what exists and what does not |
| [PRIVACY.md](PRIVACY.md) | what goes in public, and what does not |
| [REGULATION.md](REGULATION.md) | what has been examined; no lawyer has read it |
| [DISCLOSURE.md](DISCLOSURE.md) | what was built when, what came from elsewhere, what does not exist |
| [RELEASE.md](RELEASE.md) | how a release is made: one commit, one push |
| [ROLLBACK.md](ROLLBACK.md) | how to take a bad release back, surface by surface |
| [DEPENDENCY.md](DEPENDENCY.md) | what depends on one personal GitHub account, what happens if it is lost, and the plan to end it |

## What is in this repository

| folder | what it holds |
|---|---|
| [`programs-v2`](../../programs-v2) | The four programs. Each file's first lines say what it does. |
| [`programs`](../../programs) | The first deployment, exactly as deployed. |
| [`.github/workflows`](../../.github/workflows) | The workflows a repository calls, published at one pinned commit of the `workflows-<sha12>` tags of `drexthealpha/Knos` (`drexthealpha/knos-workflows` before the 0.3.34 branch). |
| [`src/knos`](../../src/knos) | What the workflows run: the judge, the relay, receipts, statements, the Stop hook, the MCP server. |
| [`crates`](../../crates), [`idl`](../../idl), [`sdk/settle`](../../sdk/settle), [`examples`](../../examples), [`conformance`](../../conformance) | What another team builds on. |
| [`web`](../../web) | The site. It reads GitHub and Solana in the browser; there is no Knos server. |
| [`terms`](../../terms) | The terms registry: each set of terms, by hash. |

## The round in full

A work order is a task, its budget and the terms that decide whether it is done, fixed before the work starts. A
bounty on an issue is the smallest one.

- A buyer who pays by invoice uses the count alone: `knos-meter` records each signed evaluation once, and moves no money.
- The seller can settle without the buyer, after a merge in a public repository: `knos settle --neutral <pull request URL>`.
- With no payment by the deadline, the amount and the fee go back, and that needs no token.
- Work can be paid without a merge only when the buyer's check runs the work as a separate program and compares its answers: of 63 cheating pull requests, plain CI passed 56 and that check passed none ([TAMPER.md](TAMPER.md)).
- Every command and term (`checks`, `paths`, `days`, `warranty`, `holdback`, `arbiter`, `/knos offer`, `/knos split`): `/knos help`, and [SECURITY.md](SECURITY.md), section 3.
- The recording of a round: [demo.mp4](https://github.com/drexthealpha/Knos/releases/latest/download/demo.mp4) (a release with no recording has no such file).

## History

Knos 0.1 (1–7 Sep 2026) was shared memory for coding agents, built on Sibyl Labs' memory engine. 0.2 and 0.3.0–0.3.9 (30 Sep – 2 Oct) tried
coordination, budgets and a jobs market before the measurement showed where the problem was ([the tag `archive/labs` of
drexthealpha/Knos](https://github.com/drexthealpha/Knos/tree/archive/labs)). 0.3.10 to 0.3.15 are the two deployments, work orders, the count and the
console.

0.3.16 put an invoice check on the site. [DISCLOSURE.md](DISCLOSURE.md) says what was built when and what came from elsewhere; [the
changelog](../../CHANGELOG.md) has every release.
