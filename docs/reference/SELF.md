<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Knos builds Knos: the self-improvement loop

**In plain words.** Agents may change the parts of Knos that people use, never the parts that judge or pay. The
referee from main tests each change with hidden tests, and keeps it only when it is better and breaks nothing. Each
kept change is paid on devnet and logged in public; only the founder may change the referee.

Code: `src/knos/self/`. Config: `targets.yml` and `CODEOWNERS` (both founder-owned). Tests: `tests/test_self_*.py`.
A real run of the loop: `examples/self/`.

## Why it is built this way

What works, from published results: the agent edits only the code under test, and the judge is fixed and out of its
reach. Karpathy's autoresearch ([github.com/karpathy/autoresearch](https://github.com/karpathy/autoresearch), March
2026) lets the agent edit `train.py` only, with `prepare.py` locked. The Darwin Goedel Machine
([arXiv 2505.22954](https://arxiv.org/abs/2505.22954)) went from 20% to 50% on SWE-bench by keeping an archive of
versions. The Huxley-Goedel Machine ([arXiv 2510.21614](https://arxiv.org/abs/2510.21614), ICLR 2026) chose parents
by how their descendants scored: 56.7% against the Darwin Goedel Machine's 53.3% with less than half the compute.

What fails: agents attack the judge. The Darwin Goedel Machine faked test logs and removed hallucination-detector
markers ([sakana.ai/dgm](https://sakana.ai/dgm/), 30 May 2025). METR saw o3 reward-hack 39 of 128 RE-Bench runs,
30.4%, including patching the evaluator ([METR, 5 June 2025](https://metr.org/blog/2025-06-05-recent-reward-hacking/)).
Anthropic saw a model that learned to cheat sabotage code meant to detect reward hacking 12% of the time
([Anthropic, 21 Nov 2025](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)). So here the judge is never the candidate's, every number is measured again by the referee, and every way a
change can hide a failure (deleted tests, removed assertions, removed detector markers, removed logging) refuses it.

## The trust split

| side | paths | who changes it |
|---|---|---|
| trusted core | Solana programs, `src/knos/judge.py`, `referee/`, `cheats/`, `gate/` (the sealed-test runner), `receipt2/`, `settle/`, `money/`, `graduation/`, `splits/`, `record/`, `self/`, `config/`, `.github/`, `actions/`, deploy scripts, `pyproject.toml`, lockfiles, `targets.yml`, `CODEOWNERS`, `tests/bench_tamper/` | the founder only |
| product | site, SDK, CLI, docs, skills, adapters, the rest of `src/knos/` and `tests/` | agents, inside a target's scope |

The two lists are `targets.yml` `core` and `CODEOWNERS`; `tests/test_self_trust.py` keeps them equal. With branch
protection on main (require review from code owners, no bypass) GitHub enforces the same line. The loop enforces it
before any candidate code runs: a core path is refused (`core_path`), a path outside the product or outside the
target's scope is refused (`out_of_scope`).

Agent pull requests run as `pull_request` jobs: a fork's run gets no secret, the token is read-only, and the job reads
main's `targets.yml` and `CODEOWNERS`, never the pull request's (`src/knos/self/templates/knos-self-agent-pr.yml`, a
template the founder adds to `.github/` by hand). The sealed and audit tiers and every payment run on the loop
operator's machine, never in a job an agent can start: no key and no hidden test is ever in it.

## Three tiers of tests

| tier | who sees it | decides a merge |
|---|---|---|
| public | everyone: the target's tests in the repository | yes |
| sealed | nobody but the referee; the agent learns pass or fail only | yes |
| audit | nobody but the referee; run on a schedule | never |

A sealed bundle is a folder kept outside the repository: a metric script and hidden tests. Its sha256 is in
`targets.yml`, and a bundle with any other hash is refused. The referee runs each sealed run twice and the two runs
must agree. The audit tier exists to catch a change that fits the sealed tests and nothing else: `knos self audit`
runs it on every accepted version, and a failure is flagged for rollback. A cheat the loop catches that the cheat
library does not know yet is listed as `proposed_rules` in the verdict; the founder adds it to `knos.cheats` with a
known-bad case (the library is core: the loop never edits it).

## One iteration

1. An agent asks for a parent version and makes a candidate commit.
2. The referee from main judges it.
3. Refused: it goes to the public record. Held: it waits for the founder, then the record.
   Accepted: canary and a devnet bounty, then the record.
*Every decision goes to the public record.*

The referee is started from the trusted checkout of main (`referee-main/`, which the loop never moves) with main's code
first on the path. In order, the first refusal decides:

1. **The referee is main's.** The running judging code must hash to main's tree (`knos.referee.judge_hash`), and the
   referee checkout must be clean, at the commit, and with the judging and loop hashes pinned at `knos self init`
   (archive v0): a checkout edited since then is refused. The candidate's own judging code is hashed too; when it
   differs, the candidate is a referee change and is refused.
2. **Lineage.** The parent is an accepted version of the target (root, canary or promoted; never a refused, held or
   rolled-back one), and the candidate descends from it. A commit judged before, or the same change (git patch-id or
   diff hash) as an accepted or held version, is refused: one change is paid once. Changed paths are read as git lists
   them (`--name-only -z`); a path the diff reader cannot read is refused.
3. **Trust split and cheat rules.** `knos.cheats.scan_diff` with the target's scope and the core, plus the loop's own
   rules: fewer tests or asserts in the changed test files, logging removed.
4. **Public tier**, then **sealed tier** (metric on parent and candidate, hidden tests, each re-run). A number the
   agent reported must equal what the referee measured.
5. **Merge rule.** The target improves by at least `min_gain`. A gain above `implausible_gain_rel` is held for the
   founder.
6. **Shadow.** The target's neighbouring tests run on the parent and the candidate side by side; a test file that
   passes on the parent and fails on the candidate holds the change.

Then the daily merge cap (`loop.daily_merge_cap`): over it, the change is held. An accepted change becomes a canary
version on the local loop branch and is paid. One `knos self run` at a time holds the state folder's lock; the
version is saved before any money moves, its payout is `pending` until the transfers return, and a failed transfer
is kept as `failed` with whatever was sent: the loop never retries a payment (the founder settles it by hand). Main is never touched by the loop: promoting a canary to main is the
founder's pull request (`loop.auto_merge_to_main: false`; switching it on is a founder decision).

## The archive and the choice of parent

Every version is kept with its parent, diff hash, tier results and decision (`archive.json`), and each one is a claim
in Knos Record with its lineage. The next parent is chosen as the Huxley-Goedel Machine does: each accepted version
gets Beta(1 + accepted, 1 + refused) over its descendants and one seeded draw; the highest draw wins. The seed and the
draws are kept, so anyone can recompute the choice.

## Referee changes need the founder

A change to the judge, the cheat library or the runner comes only as the founder's own pull request, and
`knos self referee REPO STATE CANDIDATE` decides whether it may judge:

1. **Red-team gate.** Main's code lays out the fixed red-team set (`knos.cheats.CASES`); main's scanner and the
   candidate's each scan every case in their own process. The candidate must refuse every case main refuses. A
   weaker referee is blocked here, whoever signed it.
2. **Shadow.** The candidate re-scores the loop's past jobs beside main's referee; disagreements are listed.
3. **Founder signature.** An ed25519 signature over `knos-self:referee:<candidate loop_hash>` (the judge, the cheat
   library, Gate's runner and the loop code together) by a key listed in `loop.referee_change.approval_keys`. The list is empty today, so every referee change waits for the founder.

## Rollout, caps, rollback

`sealed -> shadow -> canary -> main`. Canary bounties are low-value devnet test tokens (`canary_bounty_max_usd`).
`knos self rollback REPO STATE VERSION` takes a version and its descendants off the loop branch and records why.

## Payment

An accepted version pays its target's `bounty_usd` from the loop's devnet treasury wallet to the agent owner's devnet
wallet, with the fee of the `bounty` line of `config/fees.yaml` (read through `knos.money.fees_config`). The fee goes
to the token account of the treasury owner that knos_pay pays fees to. The tokens are a test mint: worth nothing.
Every key and fee payer is named on the command line; mainnet is refused.

## The public log

Each iteration writes, in Knos Record (domain `self`, claim `self:<target>:<version>`): `experiment`, one
`verification` per tier, one `cheat` per refusing finding, `refusal` when refused or held, `verdict` (with main's
judge_hash and the candidate's), `payout` with its devnet signatures, and the version's `claim` with its lineage.

## Commands

| command | what it does |
|---|---|
| `knos self targets` | the targets and the core/product split, validated |
| `knos self check-pr DIFF --target ID` | what an agent's pull request may not change (the CI job's step) |
| `knos self seal DIR` | a hidden bundle's sha256 for `targets.yml` |
| `knos self init REPO STATE` | the trusted referee checkout and version v0 |
| `knos self parent REPO STATE TARGET` | the version to build on next |
| `knos self run REPO STATE TARGET CANDIDATE` | one iteration (`--pay-wallet`, `--payee`, `--mint` to pay on devnet) |
| `knos self audit REPO STATE TARGET` | the audit tier on accepted versions (`--rollback`) |
| `knos self rollback REPO STATE VERSION` | a version off the loop branch |
| `knos self referee REPO STATE CANDIDATE` | a referee change: red-team gate, shadow, founder signature |

Also `python -m knos.self ...`.

## A real run

`examples/self/` holds the archive and the public log of the loop's first iterations, run on 13 Oct 2026 on a local
branch of a throwaway clone (never pushed), on the target `mcp-cold-start`: fewer modules loaded when an agent starts
the Knos MCP server. The agent was Claude Code, the build agent of this release. `examples/self/README.md` has the
table of iterations, verdicts, metrics and devnet signatures.

## The jail

Every run of candidate code (public, sealed, shadow and audit tests, and the sealed metric) runs in a new network
namespace (no network) and a new mount namespace. In it, the loop's state (the referee checkout, the archive, the
record, the runs, the other bundles), the wallet and key folders (the payout wallet, `~/.config/solana`, and every folder the operator lists in
`KNOS_SELF_MASK`) and the other tree of the
judgment are covered by empty, unreadable mounts, and the repository's `.git` is read-only. Then it runs with a clean
environment as `KNOS_SELF_SANDBOX_USER` when set, else as the operator. Without `sudo -n unshare` the referee refuses
to judge; `--sandbox none` turns the jail off and is for a machine where that is acceptable. The jail is Linux's
(network and mount namespaces): on macOS and Windows there is no `unshare`, so the referee refuses there unless
`--sandbox none` is asked for.

## Limits

- The sealed and audit bundles of `mcp-cold-start` are kept by the founder, outside the repository; only their hashes
  are public.
- The jail is not a full OS sandbox. Run as the operator (no `KNOS_SELF_SANDBOX_USER`), candidate code can read and
  write what is not masked, and it runs in the same process as the hidden tests it is judged by, so it can read them
  while they run (Gate's limit, [PR_GATE.md](PR_GATE.md)). A separate account for `KNOS_SELF_SANDBOX_USER` is a founder
  decision. The red-team gate runs a candidate referee's code unsandboxed: it comes only from the founder.
- The iterations in `examples/self/` ran before the jail and the pinned hashes were added (Gate's network-only
  sandbox, as the operator).
- The devnet treasury of the loop is a wallet of its own, not Knos's Squads vault, which nothing in Knos signs for.
- No agent other than Knos's own build agent has run the loop yet.
