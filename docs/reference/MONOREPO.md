# One repository: what was folded into Knos, and the cutover that is left

Since 0.3.31 everything Knos ships lives in drexthealpha/Knos. This page says, for each repository that Knos used to
depend on, whether its content is now a folder of Knos, why it is not yet, and what still points at it.

The old repositories stay until the founder deletes them: deleting is his action, and some of them are still called
by commits pinned by sha in other people's repositories and by escrows on devnet.

Three kinds, decided from what reads them:

- **(a) a folder**: nothing outside Knos checks where the files are. Moved, every reference updated.
- **(b) a trust anchor**: an escrow on chain or a terms document names the repository, by the sha256 of its
  `owner/name` and a commit. Moving it changes what an order trusts, so the new home runs beside the old one.
- **(c) a template**: the site or the CLI made a user's repository from it with "Use this template". Replaced by
  "create an empty repository, then add the files from a Knos folder". Knos creates a repository only when the user
  runs the command that does (`knos claim`, `examples/witnessed/witness.py`); the site only links to GitHub's forms.


**One branch (16 Oct 2026).** drexthealpha/Knos has one branch, `main`. The branches `workflows`, `oidc-rotate` and `labs` of 15 Oct were replaced by tags that keep the same commits: `workflows-<sha12>` (every published set), `oidc-rotate-<sha12>` and `archive/labs`; every other old branch whose commits were not in `main` is kept as `archive/<name>`. The steps below that name `refs/heads/...` are the record of 15 Oct.
## The table

| Repository | Kind | Where it is now | Status | Still points at the old repository |
| --- | --- | --- | --- | --- |
| knos-wanted | a | [`apps/wanted/`](../../apps/wanted) | folded; its tests run against this tree (`tests/test_fold_wanted.py`); since 0.3.33 it is Knos's demand check ([DEMAND_CHECK.md](DEMAND_CHECK.md)) | nothing in Knos; the public repository is the old copy |
| knos-task | c | [`templates/knos-task/`](../../templates/knos-task) | folded; the site's task form adds the callers to an empty repository (`web/task.js`) | the live site until this release deploys; old copies of `witness.py` |
| knos-attest | c | [`templates/knos-attest/`](../../templates/knos-attest) | folded; `python -m knos.host_judge link` then `editor` | the live site until this release deploys |
| knos-claim | c | [`templates/knos-claim/`](../../templates/knos-claim) | folded; `knos claim` creates the empty repository and commits the file; `#payee` links to both steps | knos 0.3.28 and older try the template first and fall back to the same empty repository and file |
| knos-claim-org | c | [`templates/knos-claim-org/`](../../templates/knos-claim-org) | folded; `knos claim --org` never used the template | nothing |
| knos-workflows | b | the `workflows-<sha12>` tags of drexthealpha/Knos, the same commits: 96b243f1 and its 16 ancestors, tags `workflows-<sha12>` for every commit an open escrow pins (made 15 Oct 2026, pushed with the 0.3.34 branch) | 0.3.34 branch: every caller, example, template, site page, `sdk/settle` and terms 3 document (version 2) names `drexthealpha/Knos/.github/workflows/...@96b243f1...`; `scripts/release.py workflows` commits into a worktree of the branch. `main` (tag v0.3.28, the Colosseum entry) still names the old repository until 5 Dec 2026 | the escrows funded through it (below; the last open one frees itself 2026-11-13 15:48 UTC), `main` until 5 Dec 2026, outside repositories that installed Knos. Deletable from 6 Dec 2026 at the earliest |
| knos-workflows-rc | b (devnet rehearsal only) | [`rehearsals/knos-workflows-rc/`](../../rehearsals/knos-workflows-rc) (main at 876f3ced, byte for byte); also regenerable: `python scripts/pinned_workflows.py build DIR --source REQ` | copied (0.3.34) | one open devnet job and one credits account (below) |
| knos-playground | a, into Knos's own issues (founder's decision, 14 Oct 2026) | Knos's own issues: `knos.playground.REPO`, the worker's `KNOS_FAUCET_REPO` default and every site page name drexthealpha/Knos; `python scripts/small_repos.py fold` writes its files into Knos (the issue template, `words.py`, `check.py`, `tasks/<task>.py`, `.knos/acceptance/1..200/`) | 0.3.34 branch: moved; live in Knos once the branch reaches `main` (after 5 Dec 2026). Waits: the founder opens and pins the issue labelled `faucet` in Knos and gives Knos the secrets `KNOS_FAUCET_KEY` and `KNOS_RELAY_KEY` ([FAUCET.md](FAUCET.md)) | the old repository is frozen: 35 open 5-test-USDC orders on its issues #3 and #6 to #29, the last refundable 2026-11-13 15:48 UTC; tag v0.3.28 links it until 5 Dec 2026. Deletable from 6 Dec 2026 |
| knos-rc | not foldable | it is a staging copy of Knos itself | kept; since 0.3.34 `.github/workflows/hermetic.yml` runs in Knos too, and these are cited from Knos runs (15 Oct 2026, branch knos-0.3.34): the kind cluster's token (outcome-k8s.yml, run 38701801687: OUTCOMES.md, VERIFIER.md, CAPABILITIES.md, docs/capabilities.json), the fuzz count and Kani's proof (program.yml, run 38701807179: docs/bench.json, docs/facts.json, docs/kani.json, ASSURANCE.md, TRUST.md), and the relay's event run (worker.yml, run 37716553935 of 8 Oct: RELAY.md) | still cited from it: `tests_passing` in docs/bench.json (Knos's tests.yml run 38701796582 failed: sibyl-memory-client 0.9.0 asks for an account), REPRODUCE.md's own run (filed on a branch, with a pull request), BENCH.md's two `knos-rc, comment ...` rows (events in its issues), `scripts/exercise_public.py`'s staging rehearsal |
| knos-labs | a, as history | the tag `archive/labs` of drexthealpha/Knos: its one commit ed6136f9 (fetched 15 Oct 2026 as the local branch `labs-src`) plus one commit that removes its `.github/workflows` (see "knos-labs" below) | 0.3.34 branch: CHANGELOG.md, DISCLOSURE.md, docs/reference/README.md and `knos init`'s note link `https://github.com/drexthealpha/Knos/tree/archive/labs`. Waits: that commit and the push of `labs`, with this release | tag v0.3.28 links it until 5 Dec 2026. Deletable from 6 Dec 2026, once `labs` is pushed |
| knos-oidc-rotate | b | [`workflows/knos-oidc-rotate/`](../../workflows/knos-oidc-rotate) (a copy, inactive); its commits go to the `oidc-rotate-<sha12>` tags of drexthealpha/Knos ([CUTOVER-0331.md](CUTOVER-0331.md) section 2 step 1) | copied; the 0.3.35 builds of knos_oidc and knos_pay accept both homes (`ROTATE_REF_KNOS`, `CLAIM_REF_KNOS`; tested) and are written to devnet buffers held by the upgrade vault (knos_oidc `dJA4mokfAqG7eTKUrD1MawKbWPJrzjc72qehpujiy6V`, knos_pay `C7MrKvNU2yxMG5RJqzCkCDGowe5T1R69j3LXz3Qj1VdA`); the live programs take only the old home until the founder's upgrade executes ([deploy/upgrade-0335/STEPS.md](../../deploy/upgrade-0335/STEPS.md)) | the live programs until that upgrade; the first deployment (no upgrade authority); the rotate caller `.github/workflows/keys.yml` and the claim callers (`examples/knos-claim*.yml`, `src/knos/settle/knos-claim*.yml`, `web/payee.js`), which move only after it; every existing `knos-claim` repository |
| knos-witness | a (evidence) | [`evidence/knos-witness/`](../../evidence/knos-witness) (main at 479b0327) and [`evidence/knos-witness-acaa854d/`](../../evidence/knos-witness-acaa854d) (the commit whose `witness.json` the documents cite); its 14 commits are the local ref `evidence/knos-witness` | copied (0.3.34), byte for byte, `SOURCE.json` beside each (`tests/test_evidence_copies.py`); README.md, docs/JUDGES.md, TRANSACTION.md, FLOWS.md and judges.json link the record here | the Actions runs, issue #9 and the comment on pull request #10 that those pages link (they cannot be copied, so the links stay); `examples/witnessed/witness.py` names a person's own repository `knos-witness` |
| knos-load | a (evidence) | [`evidence/knos-load/`](../../evidence/knos-load) (main at b9615b0b, its one commit) | copied (0.3.34) | the Actions runs 37833126115 and 38012410577 that docs/load.json and LOAD.md cite (kept) |
| knos-v0329-gate | a (evidence; private) | [`evidence/knos-v0329-gate/`](../../evidence/knos-v0329-gate) (main at ccf45c30; the demo pull requests' heads in its `SOURCE.json`) | copied (0.3.34) | the Actions runs PR_GATE.md cites (private: they open for the owner only) |
| knos-v0329-outcomes | a (evidence; private) | [`evidence/knos-v0329-outcomes/`](../../evidence/knos-v0329-outcomes) (the pinned commit 509485fb) and [`evidence/knos-v0329-outcomes-b59b30f3/`](../../evidence/knos-v0329-outcomes-b59b30f3) (the data commit); local refs `evidence/knos-v0329-outcomes` and `evidence/knos-v0329-outcomes-data` | copied (0.3.34) | the Actions runs in `examples/outcomes/measured-support/demo*.json`; `demo.py --repo` and `outcome.yaml.in` name it as the repository the demo runs in |
| knos-hermes | a | [`hermes/knos-hermes/`](../../hermes/knos-hermes) (master at 11df3a96; its `[project.urls]` now name Knos) | copied as source and not built: Knos ships one package ([HERMES.md](HERMES.md)) | PyPI's page of knos-hermes 0.1.0 (its links change only with a new upload: the founder's decision); the open pull request 0xNyk/awesome-hermes-agent#382 |
| knos-e2e | the live test repository | [`rehearsals/knos-e2e/`](../../rehearsals/knos-e2e) (a snapshot of main at 0ddf601a) | kept: it is the one test repository | everything that tests against it |
| knos-e2e-202610020250 | rehearsal | [`rehearsals/knos-e2e-202610020250/`](../../rehearsals/knos-e2e-202610020250) (main at e0393fc8) | copied (0.3.34) | one devnet order (CUTOVER-0331.md); BENCH.md names its #2 and #3 |
| knos-e2e-202610020406 | rehearsal | [`rehearsals/knos-e2e-202610020406/`](../../rehearsals/knos-e2e-202610020406) (main at 4b95b012) | copied (0.3.34) | an outside contributor's open pull request (#2) |
| knos-e2e-202610020610 | rehearsal | [`rehearsals/knos-e2e-202610020610/`](../../rehearsals/knos-e2e-202610020610) (main at 2e23795c) | copied (0.3.34) | one devnet order and one credits account (CUTOVER-0331.md); an outside contributor's open pull requests (#3, #4) |
| k0615 | rehearsal | [`rehearsals/k0615/`](../../rehearsals/k0615) (main at f8cd4236) | copied (0.3.34) | an outside contributor's open pull request (#8) |

knos-oidc-rotate is a trust anchor of another kind: `programs-v2/knos_pay/src/lib.rs` (`CLAIM_REF`) and
`programs-v2/knos_oidc/src/pins.rs` (`ROTATE_REF`) compile its name into the programs, so moving it is a program
upgrade through the upgrade multisig and its time lock (below).

## knos-workflows: the in-Knos path

What the chain checks. `knos_pay` and `knos_meter` read a token's `job_workflow_ref`, hash its `owner/name`, and
compare that hash and `job_workflow_sha` with what the order, the job or the credits account stored when it was funded
(`order_judge.rs`, `pay.rs`, `fund.rs`, `meter.rs`).

The repository's name is not a program constant: it comes from the caller's `uses:` line when a comment funds, and from
`--workflow owner/name@commit` when a wallet funds. `programs-v2/program_ids.json` names no knos-workflows commit. So
no program upgrade and no Squads-signed config change is needed to move it; what changes is the name new callers write.

The new home. GitHub runs a reusable workflow named `{owner}/{repo}/.github/workflows/{file}@{ref}` from any commit
of that repository, on any branch ([reusing
workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows)). The published commits of
knos-workflows are fetched into Knos as its branch `workflows`, unchanged: the same objects, so the same shas and the
same trees.

A caller then says `drexthealpha/Knos/.github/workflows/prove.yml@96b243f1...`, the order pins
sha256("drexthealpha/Knos") and that commit, and Knos's own `.github/workflows/prove.yml` on `main` (the source,
whose install step still says KNOS_LOCK) is a different commit that pays nothing pinned there. The published files
are `on: workflow_call` only, so a branch holding them runs nothing by itself.

What was built and checked (0.3.31):

- `scripts/pinned_workflows.py` knows both homes: `home` (which one the examples name), `move drexthealpha/Knos` and
  `move drexthealpha/knos-workflows` (rewrite every caller, document, template folder and site page that names the
  published commit, at the same commit, and back; byte for byte), `branch` (prints the git commands below; runs
  nothing), and `check` refuses a tree that names the two homes at once.
- `knos.tasks.PUBLIC_WORKFLOW_HOMES` counts an order pinned to either home as funded through the public workflows.
- `knos.terms3.moved` writes the next version of a terms document whose evaluators name the new home; an order keeps
  the version it was funded on.
- `tests/test_fold_workflows.py`, in LiteSVM with the test issuer: an order pinned to drexthealpha/Knos at
  96b243f1 is paid by that run and refused (error 86, `E_WORKFLOW`) for the same commit of knos-workflows, for
  another commit of Knos and for `someone/Knos`; an order pinned to knos-workflows keeps being paid by it and refuses
  the new home; a comment whose caller names the new home funds an order pinned to it.
- On devnet (14 Oct 2026, internal dogfooding, test units of a mint of the agent's own): `knos fund-wallet
  drexthealpha/knos-e2e#279 1 --checks none --days 1 --workflow drexthealpha/Knos@e25ca40dd8b56344b4ace320d2c66c3436a2f98d`
  funded job `7AsTBnqZLXQ1GaV9m1pF5QjWb1iWCoRqmsKdmm1GFZNr` on the public knos_pay, transaction
  [`2viGqe5R...`](https://explorer.solana.com/tx/2viGqe5RJxTiq9Q8A3JGZaJmvv24X7X1sUDEmTjtizZzKTTKWf5kYV1K2Me9Ydg7MgWVMGoM3mYsD6xtKUUEsvne?cluster=devnet).
  Read back: its workflow hash is sha256("drexthealpha/Knos") and its commit 96b243f1. It cannot be paid before the
  branch `workflows` exists in Knos (a GitHub Actions token of that run needs a push to Knos); it goes back to the
  wallet at its deadline.

What still names knos-workflows (read from devnet on 14 Oct 2026 with `getProgramAccounts`, every account of the
size of a job, an order and a credits account, counted by the stored workflow hash):

| Escrow | Pinned to knos-workflows | Latest deadline among the open ones (UTC) |
| --- | --- | --- |
| jobs (knos_pay 2.0) | 5 open, 4 held | 2026-10-18 01:54 |
| orders (knos_pay 2.1) | 31 open | 2026-11-08 06:48 |
| knos_meter credits | 1 | none (a credits account has no deadline) |

Read again on 15 Oct 2026 the same way (internal dogfooding): jobs 11 open (def6ac689479 2, 96b243f1b1dd 9) and 4 held,
latest open deadline 2026-10-18 01:54; orders 39 open (b7196a2ad17c 11, 5b26b1cddeae 8, 96b243f1b1dd 8, 43c8605d155e
8, 160edd4e19fc 4), latest 2026-11-13 15:48 (35 of them on drexthealpha/knos-playground's issues); credits 1
(64b31fae2b00).

A held job waits for its payee to bind a wallet and needs no new workflow run. An open one can be paid only by a run
of knos-workflows at its pinned commit until its deadline, then it is refunded.

On `main` (v0.3.28) also pinned to knos-workflows until 5 Dec 2026: every `uses:` line in `examples/*.yml`,
`.github/workflows/knos.yml` and `knos-check.yml` of Knos, `templates/`, `web/front.js` and `web/install.js`,
`sdk/settle/README.md` and its fixtures; the 0.3.34 branch names the new home in all of them and publishes version 2
of the terms documents (version 1, which orders were funded on, is kept).

Still pinned to it everywhere: drexthealpha/knos-e2e's callers, and any outside repository that installed Knos
(GitHub code search: `"drexthealpha/knos-workflows/.github/workflows" path:.github/workflows`,
`scripts/network_stats.py` INSTALLED_QUERIES).

### The cutover

The founder's steps, with every command, are in [CUTOVER-0331.md](CUTOVER-0331.md). Nothing on chain names
knos-workflows, so no Squads proposal is part of it.

## The templates

The four folders are written by `python scripts/small_repos.py fold` from the same sources the template repositories
were built from, and `tests/test_fold_templates.py` holds each folder to them byte for byte. The template repositories
on GitHub are frozen at 0.3.28's files.

They can be deleted once the site of this release is live: `knos claim` from 0.3.28 falls back to an empty repository
and the same file when the template is gone, and `examples/witnessed/witness.py` from 0.3.31 copies
`templates/knos-task/` from the checkout it runs in.

What changed for a person (counted on the page, `web/payee.js` CLICKS): binding a wallet from `#payee` is 10 clicks
instead of 8, because the claim workflow is added by its own link (GitHub's new-file page, filled in) instead of by
a template.

Nothing else changed: the claim is still a run started by hand, with the address pasted by its owner.

## knos-labs

Its 306 files include a second, older `knos` package, a compiled program and workflows that run on `push`. Copied into
`main` they would be a second package in the product tree; pushed as a branch of Knos as they are, their push
workflows would run in Knos with Knos's secrets.

So it becomes the tag `archive/labs` with one commit that removes `.github/workflows`
([CUTOVER-0331.md](CUTOVER-0331.md) section 3). Fetched on 15 Oct 2026: main = ed6136f9e3e1, one commit, ten
workflows, of which `network.yml` (push, release, schedule), `program.yml` (push) and `tests.yml` (push, pull_request,
schedule) would start on a push, and `fuzz.yml`, `index.yml`, `worker.yml` on a schedule. Nothing in Knos runs or
imports it.

## What the 0.3.34 branch did, and what waits (15 Oct 2026)

- knos-workflows: the local branch `workflows` (= e25ca40dd8b56344b4ace320d2c66c3436a2f98d, the old repository's
  `main`) and the tags `workflows-96b243f1b1dd`, `-def6ac689479`, `-b7196a2ad17c`, `-5b26b1cddeae`, `-43c8605d155e`,
  `-160edd4e19fc`, `-64b31fae2b00` (every commit an open escrow on devnet pins, read on 15 Oct). Every published file
  of every one of those commits is `on: workflow_call`; `attest.yml` (0.3.13 on) also has `workflow_dispatch`, a run
  by hand, and none runs on a push. Then step 5 of the cutover: the callers, `web/front.js`, `web/install.js`, the
  templates, `sdk/settle`, the offers of `examples/`, and terms 3 version 2 of bug-fix, dataset-batch and migration
  name the new home. Waits: the push of the branch and the tags (with this release), the rulesets (step 2, the
  founder's), the first live payment on the new home (step 4), `main` (after 5 Dec 2026).
- knos-labs: the local branch `labs-src` = ed6136f9; the commit that removes its workflows and the push of `labs` wait.
- knos-playground: moved into Knos's own issues on this branch; its open orders on devnet free themselves by
  2026-11-13 15:48 UTC; nothing is funded there by this release's code.

## knos-oidc-rotate

Its two files, at the commit the second deployment pins last (212f9eb5), are in Knos as
[`workflows/knos-oidc-rotate/`](../../workflows/knos-oidc-rotate): the same bytes, so the same git tree
(`a7302cf6...`, held by `tests/test_fold_rotate.py`). They are not active there (they are not in Knos's own
`.github/workflows/`).

The programs name the old repository in compiled constants, so the move is a program upgrade;
[CUTOVER-0331.md](CUTOVER-0331.md) has the steps, the Squads step included. The code half is done: the 0.3.35 builds
accept the old home and Knos's (`ROTATE_REF_KNOS`, `CLAIM_REF_KNOS`, exact prefixes, look-alikes refused in
`tests/test_two_homes_*.py`), and both are in devnet buffers held by the upgrade vault.

What waits for the founder: the two proposals, their approval and time lock, execution, and only then the rotate and
claim callers ([deploy/upgrade-0335/STEPS.md](../../deploy/upgrade-0335/STEPS.md)).
