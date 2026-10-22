# Cutover 0.3.31: the repositories that still live outside Knos

The founder's steps, with every command, for the repositories [MONOREPO.md](MONOREPO.md) could not simply copy: the
two trust anchors (knos-workflows, knos-oidc-rotate), and knos-labs, knos-playground, knos-rc. Old repositories stay
until the step that deletes them, and deleting is his action.

What the 0.3.34 branch (ONE-KNOS, 15 Oct 2026) did and what still waits is said under each section ("Done on the
0.3.34 branch"); `main` and tag v0.3.28, the Colosseum entry, are untouched until 5 Dec 2026, so no repository they
link to is deleted before 6 Dec 2026.


**One branch (16 Oct 2026).** drexthealpha/Knos has one branch, `main`. The branches `workflows`, `oidc-rotate` and `labs` of 15 Oct were replaced by tags that keep the same commits: `workflows-<sha12>` (every published set), `oidc-rotate-<sha12>` and `archive/labs`; every other old branch whose commits were not in `main` is kept as `archive/<name>`.

The steps below that name `refs/heads/...` are the record of 15 Oct.
## What still points at the old repositories

Read from devnet on 14 Oct 2026 (`getProgramAccounts` on the public knos_pay and knos_meter, every account of a job's,
an order's and a credits account's size, counted by the workflow hash it stores; internal dogfooding of this build):

| Old repository | What names it | Count | Latest open deadline (UTC) |
| --- | --- | --- | --- |
| knos-workflows | knos_pay 2.0 jobs | 5 open, 4 held | 2026-10-18 01:54 |
| knos-workflows | knos_pay 2.1 orders | 31 open | 2026-11-08 06:48 |
| knos-workflows | knos_meter credits | 1 | none (credits have no deadline) |
| knos-workflows-rc | knos_pay jobs; knos_meter credits | 1 open; 1 | 2026-10-17 15:37 |
| knos-e2e-202610020610 | knos_pay orders; knos_meter credits | 1 open; 1 | 2026-10-21 03:39 |
| knos-e2e-202610020250 | knos_pay orders | 1 open | 2026-10-14 13:18 |

Read again on 15 Oct 2026 the same way: knos-workflows 11 open and 4 held jobs (latest 2026-10-18 01:54), 39 open
orders (latest 2026-11-13 15:48; 35 of them on knos-playground's issues), 1 credits account; knos-workflows-rc 1 open
job (2026-10-17 15:37) and 1 credits account; knos-e2e-202610020610 1 open order (2026-10-21 03:39) and 1 credits
account; knos-e2e-202610020250 none open.

Pinned in files and settings, not on chain:

- knos-workflows: every `uses:` line of `examples/*.yml`, Knos's own `.github/workflows/knos.yml` and `knos-check.yml`,
  `templates/`, `web/front.js`, `web/install.js`, `sdk/settle/README.md` and `sdk/settle/fixtures.json`; the terms
  documents `terms/3/bug-fix/1.json`, `terms/3/dataset-batch/1.json`, `terms/3/migration/1.json`; drexthealpha/knos-e2e,
  drexthealpha/knos-playground and the template repositories' callers; every outside repository that installed Knos.
- knos-oidc-rotate: `ROTATE_REF` (`programs-v2/knos_oidc/src/pins.rs`, and `programs/knos_oidc/src/pins.rs` of the
  first deployment, which is immutable), `CLAIM_REF` (`programs-v2/knos_pay/src/lib.rs`, used by Bind and BindOrg),
  `src/knos/settle/v2/relay/pins.py`, `src/knos/mainnet_check.py` (`PINS_REPO`), `src/knos/proof/ghrelay.py`
  (`ROTATE_REPO`), `scripts/oidc_pins.py`, `examples/knos-claim.yml`, `examples/knos-claim-org.yml`, `templates/knos-claim*`,
  and every person's and organisation's `knos-claim` repository.
- `programs-v2/program_ids.json` holds `rotate_sha`, `rotate_sha2`, `claim_sha` and `claim_sha_org` (commits, which do
  not change with the move) and `attest_repo_ids` [1353152983 Knos, 1401432540 knos-oidc-rotate]: Knos is already one
  of the two repositories a rotate run may happen in.

## 1. knos-workflows (no Squads step)

Nothing on chain names knos-workflows: an order stores the hash of the repository its caller named. So the move is a
branch of Knos holding the same commits, then new callers naming it.

1. Put the published commits into Knos, unchanged (`python scripts/pinned_workflows.py branch` prints these):

   ```
   git fetch https://github.com/drexthealpha/knos-workflows.git main
   git merge-base --is-ancestor e25ca40dd8b56344b4ace320d2c66c3436a2f98d FETCH_HEAD
   git branch workflows FETCH_HEAD
   git tag workflows-e25ca40dd8b5 e25ca40dd8b56344b4ace320d2c66c3436a2f98d
   git push origin workflows workflows-e25ca40dd8b5
   ```

2. Protect the branch and its tags so no commit a caller names can become unreachable: a ruleset on
   drexthealpha/Knos for `refs/heads/workflows` and `refs/tags/workflows-*` with deletion and non-fast-forward
   blocked ([rulesets](https://docs.github.com/en/rest/repos/rules#create-a-repository-ruleset)):

   ```
   gh api -X POST repos/drexthealpha/Knos/rulesets --input - <<'JSON'
   {"name": "published workflows", "target": "branch", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/heads/workflows"], "exclude": []}},
    "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}]}
   JSON
   gh api -X POST repos/drexthealpha/Knos/rulesets --input - <<'JSON'
   {"name": "published workflow tags", "target": "tag", "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/workflows-*"], "exclude": []}},
    "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}, {"type": "update"}]}
   JSON
   ```

3. Check: `git ls-remote origin refs/heads/workflows refs/tags/workflows-e25ca40dd8b5` names
   e25ca40dd8b56344b4ace320d2c66c3436a2f98d. The same commit sha is the same tree, byte for byte.
4. The first live payment on the new home, in drexthealpha/knos-e2e only: on a test branch whose callers say
   `drexthealpha/Knos/.github/workflows/...@96b243f1...`, fund an issue by comment and pay its pull request the way
   the canary does; read the order's workflow hash. This is the step this build could run only in LiteSVM.
5. In the next release: `python scripts/pinned_workflows.py move drexthealpha/Knos`, `python scripts/small_repos.py
   fold`, `python scripts/front_workflow.py`, and publish version 2 of each `terms/3` document with
   `knos.terms3.moved`. From then on `scripts/release.py workflows` writes into a worktree of the `workflows-<sha12>` tags
   (commit, tag `workflows-<sha12>`, push) instead of a checkout of knos-workflows.
6. Every repository that installed Knos updates its two callers to the new home. Where Knos Gate guards the
   repository, a pull request that edits `.github/workflows/` is refused (`gate.workflow_edited`): the owner commits
   the change to the default branch directly.
7. knos-workflows stays until the last open escrow pinned to it is paid or refunded (2026-11-08 06:48 UTC on the
   count above, later if more are funded through it) and no outside caller names it. Then, and only then:
   `gh repo delete drexthealpha/knos-workflows --yes`. Deleting it earlier makes every open escrow pinned to it
   unpayable and breaks every repository that still calls it.

Done on the 0.3.34 branch (15 Oct 2026). Steps 1 and 3, locally in the coordinator's clone: `workflows` =
96b243f1b1dd5c975a0318dd9709a0da22b98dcd (the old repository's `main`, 17 commits, the pinned commit is its tip), tag
`workflows-96b243f1b1dd`, and a tag `workflows-<sha12>` for every other commit an open escrow pins: def6ac689479,
b7196a2ad17c, 5b26b1cddeae, 43c8605d155e, 160edd4e19fc, 64b31fae2b00.

No terms document and no program id names a commit of it. Every workflow file on every commit of the branch is `on:
workflow_call`; `attest.yml` (0.3.13 on) is also `workflow_dispatch` (a run by hand by someone who can write to Knos),
and none runs on a push.

Step 5: done in this branch's tree (`move`, `fold`, `front_workflow.py`, terms 3 version 2 of bug-fix, dataset-batch and
migration, and `release.py workflows` writing into a worktree of `workflows`; `pinned_workflows.py check` passes).

Waits: the push of `workflows` and its tags (the release's one push), step 2 (the founder's rulesets), step 4 (the first
live payment on the new home), `main` (after 5 Dec 2026), step 6 (outside repositories), step 7 (from 6 Dec 2026, after
the last open escrow above, 2026-11-13 15:48 UTC).


## 2. knos-oidc-rotate (a program upgrade, signed through Squads)

The programs compile `drexthealpha/knos-oidc-rotate/.github/workflows/rotate.yml@` (ROTATE_REF) and
`.../claim.yml@` (CLAIM_REF). The same branch idea keeps the commits (6ddf031b, 80e796d3, 212f9eb5) and so the
`rotate_sha*` and `claim_sha*` pins; only the repository part of the two constants changes, and only by an upgrade.

Where this stands (0.3.35 builds, branch knos-0.3.34):

- Done, step 2: the code accepts both prefixes. `programs-v2/knos_oidc/src/pins.rs` has `ROTATE_REF_KNOS` and
  `rotate_ref`, `programs-v2/knos_pay/src/lib.rs` has `CLAIM_REF_KNOS` and `claim_ref` (used by Bind in `pay.rs` and
  BindOrg in `order_judge.rs`), and `src/knos/settle/v2/relay/pins.py` has the same two prefixes. `knos mainnet-check`
  takes a pinned commit from either home (`PINS_REPOS`), and the relay reads key tokens on the issues of both
  (`ghrelay.ROTATE_REPOS`). LiteSVM tests on the testkeys builds: `tests/test_two_homes_rotate.py`,
  `tests/test_two_homes_claim.py` (both homes; `someone/Knos`, `drexthealpha/Knos-x`, `drexthealpha/Knosx`,
  `drexthealpha/knos` and other look-alikes refused; the builds before the change refuse the Knos home), and
  `tests/test_two_homes_relay.py`.
- Done, step 3 up to the founder's signatures: both programs built with the pinned toolchain (sBPF v3,
  cargo-build-sbf 4.4.0, platform-tools v1.57; two builds in two checkouts gave the same bytes) and written to devnet
  buffers whose authority is the upgrade vault: knos_oidc `dJA4mokfAqG7eTKUrD1MawKbWPJrzjc72qehpujiy6V` (executable hash `925c76f051f9c28f617dc18352fcdab6127b2d23b164eb87fcab282e02bbe968`), knos_pay
  `C7MrKvNU2yxMG5RJqzCkCDGowe5T1R69j3LXz3Qj1VdA` (`e01605411369b40b9e6fd28595d0254f06357fbf7f5c887eef207f8d5b68ad3a`). They supersede the knos_oidc buffer `3xBgKGynRGRLCs2ShYsyAdNucLbE3KjvMFnKFJoiPiyr` and
  the knos_pay buffer `Dfo5pYRLY8z9yvuXDQjJQtaoqJeL7Atso8zhWy9Ehkfj`.
  [deploy/upgrade-0335/STEPS.md](../../deploy/upgrade-0335/STEPS.md) has every command: check the bytes, propose, the
  time lock, execute with `--expect-hash`, and the buffers not to propose.
- Waiting for the founder: the two proposals and their approvals, the time lock, execution; then step 4. The first
  deployment (`programs/knos_oidc`, no upgrade authority) is left as it is.

1. Put the commits into Knos, unchanged, and protect them as in step 2 above (ref `refs/heads/oidc-rotate`, tags
   `oidc-rotate-*`):

   ```
   git fetch https://github.com/drexthealpha/knos-oidc-rotate.git main
   git merge-base --is-ancestor 212f9eb5f584eb6f8cd2d6673878132fc0011e27 FETCH_HEAD
   git branch oidc-rotate FETCH_HEAD
   git tag oidc-rotate-212f9eb5f584 212f9eb5f584eb6f8cd2d6673878132fc0011e27
   git tag oidc-rotate-80e796d341f6 80e796d341f65060767939c4e65a38ede5fa1ac8
   git tag oidc-rotate-6ddf031b64fe 6ddf031b64febecfcd510763ecee37637a8047fa
   git push origin oidc-rotate oidc-rotate-212f9eb5f584 oidc-rotate-80e796d341f6 oidc-rotate-6ddf031b64fe
   git rev-parse 212f9eb5f584eb6f8cd2d6673878132fc0011e27^{tree}     # a7302cf65b15dc2b9280217a3b47239ac7527d48 = workflows/knos-oidc-rotate/
   ```

2. Code (a PLATFORM change, reviewed like any program change): accept BOTH repository prefixes, never only the new
   one, so keys and binds keep working through the transition. `pins.rs`: a second constant
   `ROTATE_REF_KNOS = b"drexthealpha/Knos/.github/workflows/rotate.yml@"` checked beside ROTATE_REF with the same
   ROTATE_SHA/ROTATE_SHA2; `knos_pay/src/lib.rs`: `CLAIM_REF_KNOS = b"drexthealpha/Knos/.github/workflows/claim.yml@"`
   beside CLAIM_REF in `pay.rs` `bind` and `order_judge.rs` BindOrg; `src/knos/settle/v2/relay/pins.py` the same two
   prefixes; LiteSVM tests for both prefixes and for a look-alike (`someone/Knos`). `ATTEST_REPO_IDS` needs no change.
3. Build with the pinned toolchain (`scripts/build_sbf*.sh`), write both programs to buffers, set each buffer's
   authority to the upgrade vault `CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2`, and create one Squads v4 vault
   transaction per program on the upgrade multisig `9HcsMEo2o6zZu9t1kbFWpnyKn7hiHaZYYFwNHZSpmWqK` (BPF Upgradeable
   Loader `Upgrade`: program, buffer, spill, vault). Two of the three members approve (the founder's keys); the 8-day
   time lock (programs-v2/README.md, GOVERNANCE.md) runs before execution; then execute. Agents never sign this.
4. After execution: a caller in Knos `main`, `.github/workflows/oidc-rotate.yml`, `on: schedule` and
   `workflow_dispatch`, `uses: drexthealpha/Knos/.github/workflows/rotate.yml@212f9eb5f584eb6f8cd2d6673878132fc0011e27`
   with `id-token: write` and `issues: write`; watch one scheduled run's keys reach knos_oidc. Then the claim callers
   (`examples/knos-claim*.yml`, `templates/knos-claim*`) name `drexthealpha/Knos/.github/workflows/claim.yml@...`.
   The exact files, and the tests that change with them, are in section 4 of
   [deploy/upgrade-0335/STEPS.md](../../deploy/upgrade-0335/STEPS.md).
5. knos-oidc-rotate stays while anything can still need it: the first deployment (no upgrade authority) accepts only its old
   path, every existing `knos-claim` repository calls it, and the keys of the second deployment expire unless a rotate
   run names them again. Deleting it is the last step, and only when the founder decides the first deployment and the
   old claim callers no longer matter: `gh repo delete drexthealpha/knos-oidc-rotate --yes`.

## 3. knos-labs (a branch, with one commit of the founder's)

Not load-bearing. Its push-triggered workflows must not arrive in Knos as they are, so the branch gets one commit that
removes them:

```
git fetch https://github.com/drexthealpha/knos-labs.git main
git checkout -b labs FETCH_HEAD
git rm -r -q .github/workflows
git commit -m "knos-labs: the earlier experiments, kept as history; their workflows removed"
git push origin labs
```

then change the two links (CHANGELOG.md, DISCLOSURE.md) to `https://github.com/drexthealpha/Knos/tree/archive/labs` and delete
the repository. Nothing in Knos runs or imports it.

Done on the 0.3.34 branch (15 Oct 2026): fetched, main = ed6136f9e3e1dd45b3d0c97facd1608b98175625 (one commit, 306 files),
kept as the local branch `labs-src`; its `.github/workflows`: fund.yml, prove.yml, relay.yml (workflow_call), prove-demo.yml
(workflow_dispatch), fuzz.yml, index.yml, worker.yml (schedule, workflow_dispatch), network.yml (push, release, schedule,
workflow_dispatch), program.yml (push, workflow_dispatch), tests.yml (push, pull_request, schedule, workflow_dispatch). The
links in CHANGELOG.md, DISCLOSURE.md, docs/reference/README.md and `knos init`'s note name
`https://github.com/drexthealpha/Knos/tree/archive/labs`.

Waits: the commit that removes `.github/workflows` and the push of `labs` (the release's one push), then the deletion, from
6 Dec 2026 (tag v0.3.28 links it).

## 4. knos-playground and knos-rc (not folded)

- knos-playground is where strangers open issues that fund test tasks from the faucet; its files are already written
  from Knos (`python scripts/small_repos.py build knos-playground DIR`). Moving it into Knos's own issues is a product
  decision (strangers' test issues and pull requests in the product repository), then: `knos.playground.REPO`, the
  worker's `KNOS_FAUCET_REPO`, `web/playground.js`, `web/buyer.js`, `web/install.js` and `web/passkey_fund.js`
  (FAUCET_ISSUE), `src/knos/claim_guard.py`, `src/knos/commands.py` (FAUCET_WHERE), `src/knos/controls.py`, and
  waiting until its open funded tasks are paid or refunded.

Done on the 0.3.34 branch (15 Oct 2026; the founder decided yes on 14 Oct): every constant and page above names
drexthealpha/Knos, and so do `scripts/pages_data.py`, `scripts/exercise_public.py`, `scripts/task_board.py`,
`examples/witnessed/witness.py`, the console's sample and the docs.

`python scripts/small_repos.py fold` writes the playground's files into Knos (the issue template
`fund-a-test-task.md`, `words.py`, `check.py`, `tasks/<task>.py` and their public examples, the starter checks under
`.knos/acceptance/1..200/`). The faucet is the `faucet` job of Knos's own `worker.yml`.

`FAUCET_ISSUE` and `FAUCET_WHERE` list the faucet issue by its label, so no number is written.

Waits: the founder opens one issue in drexthealpha/Knos titled "Faucet: test USDC for your first task", labels it
`faucet` and pins it, and adds the secrets `KNOS_FAUCET_KEY` and `KNOS_RELAY_KEY` to Knos ([FAUCET.md](FAUCET.md)),
when the branch reaches `main` (after 5 Dec 2026).

knos-playground's 35 open orders free themselves by 2026-11-13 15:48 UTC; it can be deleted from 6 Dec 2026. - knos-rc
is the staging copy of Knos itself.

Since 0.3.34 `.github/workflows/hermetic.yml` runs in Knos too, and docs/kani.json, docs/capabilities.json,
docs/facts.json, the fuzz count in docs/bench.json, OUTCOMES.md, RELAY.md and VERIFIER.md cite runs of Knos
([MONOREPO.md](MONOREPO.md), its row). Still cited from knos-rc: `tests_passing` in docs/bench.json (re-source it
from a green tests.yml run of Knos), REPRODUCE.md's own run, two rows of BENCH.md and the staging rehearsal of
`scripts/exercise_public.py`.

Re-source the first two, then delete it.

## 5. The template repositories and knos-wanted

knos-task, knos-attest, knos-claim, knos-claim-org: nothing of this release uses them. Delete them once this
release's site is live (`gh repo delete drexthealpha/<name> --yes`). knos-wanted: apps/wanted/ is the app; delete the
repository once this release is pushed and its tests are green there.
