# One repository: what was folded into Knos, and the cutover that is left

Since 0.3.31 everything Knos ships lives in drexthealpha/Knos. This page says, for each repository that Knos used to
depend on, whether its content is now a folder of Knos, why it is not yet, and what still points at it. The old
repositories stay until the founder deletes them: deleting is his action, and some of them are still called by
commits pinned by sha in other people's repositories and by escrows on devnet.

Three kinds, decided from what reads them:

- **(a) a folder**: nothing outside Knos checks where the files are. Moved, every reference updated.
- **(b) a trust anchor**: an escrow on chain or a terms document names the repository, by the sha256 of its
  `owner/name` and a commit. Moving it changes what an order trusts, so the new home runs beside the old one.
- **(c) a template**: the site or the CLI made a user's repository from it with "Use this template". Replaced by
  "create an empty repository, then add the files from a Knos folder". Knos creates a repository only when the user
  runs the command that does (`knos claim`, `examples/witnessed/witness.py`); the site only links to GitHub's forms.

## The table

| Repository | Kind | Where it is now | Status | Still points at the old repository |
| --- | --- | --- | --- | --- |
| knos-wanted | a | [`apps/wanted/`](../../apps/wanted) | folded; its tests run against this tree (`tests/test_fold_wanted.py`); since 0.3.33 it is Knos's demand check ([DEMAND_CHECK.md](DEMAND_CHECK.md)) | nothing in Knos; the public repository is the old copy |
| knos-task | c | [`templates/knos-task/`](../../templates/knos-task) | folded; the site's task form adds the callers to an empty repository (`web/task.js`) | the live site until this release deploys; old copies of `witness.py` |
| knos-attest | c | [`templates/knos-attest/`](../../templates/knos-attest) | folded; `python -m knos.host_judge link` then `editor` | the live site until this release deploys |
| knos-claim | c | [`templates/knos-claim/`](../../templates/knos-claim) | folded; `knos claim` creates the empty repository and commits the file; `#payee` links to both steps | knos 0.3.28 and older try the template first and fall back to the same empty repository and file |
| knos-claim-org | c | [`templates/knos-claim-org/`](../../templates/knos-claim-org) | folded; `knos claim --org` never used the template | nothing |
| knos-workflows | b | the branch `workflows` of drexthealpha/Knos, the same commits (after the cutover below) | in-Knos path built and tested; old repository is the live one | every caller and every escrow below |
| knos-workflows-rc | b (devnet rehearsal only) | regenerable: `python scripts/pinned_workflows.py build DIR --source REQ` | nothing to fold | one open devnet job and one credits account (below) |
| knos-playground | not foldable yet | its files are written from Knos already (`scripts/small_repos.py build knos-playground`) | a live service: strangers open issues there to fund test tasks | open faucet tasks on its issues; `knos.playground.REPO`; the worker's `KNOS_FAUCET_REPO` default |
| knos-rc | not foldable | it is a staging copy of Knos itself | kept | `.github/workflows/hermetic.yml` runs only there; evidence links to its runs in docs/bench.json, docs/kani.json, docs/capabilities.json, OUTCOMES.md, RELAY.md, REPRODUCE.md, VERIFIER.md |
| knos-labs | a, but not by a copy | history only (CHANGELOG, DISCLOSURE.md, `knos init`'s note) | not folded: see "knos-labs" below | links in CHANGELOG.md and DISCLOSURE.md |
| knos-oidc-rotate | b | [`workflows/knos-oidc-rotate/`](../../workflows/knos-oidc-rotate) (a copy, inactive) | copied; the programs still pin the old repository | `ROTATE_REF` in `programs-v2/knos_oidc/src/pins.rs`, `CLAIM_REF` in `programs-v2/knos_pay/src/lib.rs`, the first deployment (no upgrade authority), `src/knos/settle/v2/relay/pins.py`, every `knos-claim` repository |

knos-oidc-rotate is a trust anchor of another kind: `programs-v2/knos_pay/src/lib.rs` (`CLAIM_REF`) and
`programs-v2/knos_oidc/src/pins.rs` (`ROTATE_REF`) compile its name into the programs, so moving it is a program
upgrade through the upgrade multisig and its time lock (below).

## knos-workflows: the in-Knos path

What the chain checks. `knos_pay` and `knos_meter` read a token's `job_workflow_ref`, hash its `owner/name`, and
compare that hash and `job_workflow_sha` with what the order, the job or the credits account stored when it was
funded (`order_judge.rs`, `pay.rs`, `fund.rs`, `meter.rs`). The repository's name is not a program constant: it
comes from the caller's `uses:` line when a comment funds, and from `--workflow owner/name@commit` when a wallet funds.
`programs-v2/program_ids.json` names no knos-workflows commit. So no program upgrade and no Squads-signed config
change is needed to move it; what changes is the name new callers write.

The new home. GitHub runs a reusable workflow named `{owner}/{repo}/.github/workflows/{file}@{ref}` from any commit
of that repository, on any branch
([reusing workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows)). The published
commits of knos-workflows are fetched into Knos as its branch `workflows`, unchanged: the same objects, so the same
shas and the same trees. A caller then says `drexthealpha/Knos/.github/workflows/prove.yml@96b243f1...`, the order
pins sha256("drexthealpha/Knos") and that commit, and Knos's own `.github/workflows/prove.yml` on `main` (the source,
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
  drexthealpha/knos-e2e#279 1 --checks none --days 1 --workflow drexthealpha/Knos@96b243f1b1dd5c975a0318dd9709a0da22b98dcd`
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

A held job waits for its payee to bind a wallet and needs no new workflow run. An open one can be paid only by a run
of knos-workflows at its pinned commit until its deadline, then it is refunded. Also pinned to knos-workflows:
every `uses:` line in `examples/*.yml`, `.github/workflows/knos.yml` and `knos-check.yml` of Knos, `templates/`,
`web/front.js` and `web/install.js`, `sdk/settle/README.md` and its fixtures, the three terms documents
`terms/3/bug-fix/1.json`, `terms/3/dataset-batch/1.json`, `terms/3/migration/1.json`, drexthealpha/knos-e2e's callers,
and any outside repository that installed Knos (GitHub code search: `"drexthealpha/knos-workflows/.github/workflows"
path:.github/workflows`, `scripts/network_stats.py` INSTALLED_QUERIES).

### The cutover

The founder's steps, with every command, are in [CUTOVER-0331.md](CUTOVER-0331.md). Nothing on chain names
knos-workflows, so no Squads proposal is part of it.

## The templates

The four folders are written by `python scripts/small_repos.py fold` from the same sources the template
repositories were built from, and `tests/test_fold_templates.py` holds each folder to them byte for byte. The template
repositories on GitHub are frozen at 0.3.28's files. They can be deleted once the site of this release is live:
`knos claim` from 0.3.28 falls back to an empty repository and the same file when the template is gone, and
`examples/witnessed/witness.py` from 0.3.31 copies `templates/knos-task/` from the checkout it runs in.

What changed for a person (counted on the page, `web/payee.js` CLICKS): binding a wallet from `#payee` is 10 clicks
instead of 8, because the claim workflow is added by its own link (GitHub's new-file page, filled in) instead of by
a template. Nothing else changed: the claim is still a run started by hand, with the address pasted by its owner.

## knos-labs

Its 306 files include a second, older `knos` package, a compiled program and workflows that run on `push`. Copied into
`main` they would be a second package in the product tree; pushed as a branch of Knos as they are, their push
workflows would run in Knos with Knos's secrets. So it is not folded by this release; the founder's steps, when he
wants it folded, are in [CUTOVER-0331.md](CUTOVER-0331.md). Nothing in Knos runs or imports it.

## knos-oidc-rotate

Its two files, at the commit the second deployment pins last (212f9eb5), are in Knos as
[`workflows/knos-oidc-rotate/`](../../workflows/knos-oidc-rotate): the same bytes, so the same git tree
(`a7302cf6...`, held by `tests/test_fold_rotate.py`). They are not active there (they are not in Knos's own
`.github/workflows/`). The programs name the old repository in compiled constants, so the move is a program upgrade;
[CUTOVER-0331.md](CUTOVER-0331.md) has the steps, the Squads step included.
