# Upgrade 0.3.35: knos_oidc and knos_pay accept the rotate and claim workflows from Knos too

**For the founder.** Nothing here has been proposed, approved or executed, and no founder or member key signed
anything. The OK-PROG build agent changed the two programs, built them as sBPF v3 with the pinned toolchain, wrote each
build to a devnet buffer with its own test wallet, read the bytes back and handed each buffer to the upgrade vault.
Only proposals of the upgrade multisig `9HcsMEo2o6zZu9t1kbFWpnyKn7hiHaZYYFwNHZSpmWqK` that two members approve,
executed after the 691,200-second (8-day) time lock, can put these bytes into the programs.

## What changes

The programs compile the repository part of two workflow pins. They now accept BOTH homes of each workflow, the old
repository and Knos's branch `oidc-rotate` (the same commits: CUTOVER-0331.md section 2 step 1), so keys and binds
keep working while callers move. Exact prefixes: `someone/Knos/...`, `drexthealpha/Knos-x/...`,
`drexthealpha/Knosx/...` and `drexthealpha/knos/...` are refused (tests below).

| program | constant added | where it is checked | commits it takes (unchanged) |
|---|---|---|---|
| knos_oidc | `ROTATE_REF_KNOS = b"drexthealpha/Knos/.github/workflows/rotate.yml@"` (`programs-v2/knos_oidc/src/pins.rs`, `rotate_ref`) | `attested` (RegisterKey, RegisterIssuerKey, Refresh) | `ROTATE_SHA` 6ddf031b…, `ROTATE_SHA2` 212f9eb5… |
| knos_pay | `CLAIM_REF_KNOS = b"drexthealpha/Knos/.github/workflows/claim.yml@"` (`programs-v2/knos_pay/src/lib.rs`, `claim_ref`) | `pay.rs` Bind (8), `order_judge.rs` BindOrg (25) | `CLAIM_SHA` 80e796d3… (Bind, BindOrg), `CLAIM_SHA_ORG` 212f9eb5… (BindOrg) |

No instruction, account layout, error number or other rule changed. The first deployment (`programs/knos_oidc`) has
no upgrade authority and keeps taking only the old home. The builds come from branch knos-0.3.34 (511fb84b) with this
change, so the knos_pay build also carries everything of the 0.3.34 knos_pay buffer, and the knos_oidc build everything
of the 0.3.30 one.

## 0. The buffers (done; no founder SOL was needed)

| program (devnet id) | buffer | bytes | executable hash | set-buffer-authority (to the vault) |
|---|---|---|---|---|
| knos_oidc `FkwZdsYCmzicJMtHLTkPK76bYNVG4WNwkWJBiVWNtF3W` | `dJA4mokfAqG7eTKUrD1MawKbWPJrzjc72qehpujiy6V` | 173,184 | `925c76f051f9c28f617dc18352fcdab6127b2d23b164eb87fcab282e02bbe968` | `5j2QC2D46GK4i36KtWuk6CS4xvYHNNR8eDEadqmstMaTHvRXEGAFz33gp5yP1A5Ys1u8AcQ4zt3kcmScMFv1jbEZ` |
| knos_pay `5y7iWJ1VAMJjnnWbbdo2a2PsWJEwTExSNpzrvQSEnS8k` | `C7MrKvNU2yxMG5RJqzCkCDGowe5T1R69j3LXz3Qj1VdA` | 413,544 | `e01605411369b40b9e6fd28595d0254f06357fbf7f5c887eef207f8d5b68ad3a` | `5yKNyyLC1b4bm8esp8sfu8dQjTAbF7Jfd27YPo86HHvncWLF2SQK8uHhcXZXB5jLdLXakniUFHUz5KUJDfhsECSd` |

Upgrade vault (each buffer's authority): `CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2`. Written by the agent's own
devnet test wallet `DYLJkCVCqr4fM8Py4L2bSyrQYeuP6TaEJ5G7drh3WL72` (SOL consolidated from the build team's own test
wallets); each buffer's bytes were read back (`solana program dump`) and equal the build before its authority was
handed over. [HASHES-v3.txt](HASHES-v3.txt) beside this file has the file hashes too.

The builds are reproducible: two builds, in two checkouts at different paths with fresh target directories, gave the
same bytes (HASHES-v3.txt). Panic messages carry file paths and line numbers, so the hash holds only for this exact
source and the `--remap-path-prefix` flags of `scripts/build_sbf.sh`.

## 1. Check the bytes yourself

    git checkout <the commit that carries this file>
    bash scripts/build_sbf.sh v3 deploy     # cargo-build-sbf 4.4.0 + platform-tools v1.57 (SBF_ARGS=--skip-tools-install if they are installed)
    # knos_oidc's executable hash must be 925c76f051f9c28f617dc18352fcdab6127b2d23b164eb87fcab282e02bbe968
    # knos_pay's  executable hash must be e01605411369b40b9e6fd28595d0254f06357fbf7f5c887eef207f8d5b68ad3a
    solana program dump -u devnet dJA4mokfAqG7eTKUrD1MawKbWPJrzjc72qehpujiy6V oidc.so
    solana-verify get-executable-hash oidc.so      # 925c76f051f9c28f617dc18352fcdab6127b2d23b164eb87fcab282e02bbe968
    solana program dump -u devnet C7MrKvNU2yxMG5RJqzCkCDGowe5T1R69j3LXz3Qj1VdA pay.so
    solana-verify get-executable-hash pay.so       # e01605411369b40b9e6fd28595d0254f06357fbf7f5c887eef207f8d5b68ad3a
    solana program show -u devnet dJA4mokfAqG7eTKUrD1MawKbWPJrzjc72qehpujiy6V    # Authority: CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2
    solana program show -u devnet C7MrKvNU2yxMG5RJqzCkCDGowe5T1R69j3LXz3Qj1VdA    # Authority: CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2

(`scripts/build_sbf.sh v3 deploy` also rebuilds knos_meter and knos_passkey and rewrites deploy/upgrade-0329/HASHES-v3.txt;
`git checkout deploy/upgrade-0329` afterwards.)

## 2. Propose (two member keys approve; the founder signs, never an agent)

    node scripts/governance.mjs upgrade propose knos_oidc dJA4mokfAqG7eTKUrD1MawKbWPJrzjc72qehpujiy6V --ungated --out oidc-0335.json
    node scripts/governance.mjs upgrade propose knos_pay C7MrKvNU2yxMG5RJqzCkCDGowe5T1R69j3LXz3Qj1VdA --ungated --out pay-0335.json

Compare the executable hash each prints with the table. (`--ungated` because the release gate records no build of
this source; step 1 is the evidence, as for the 0.3.29, 0.3.30 and 0.3.34 v3 buffers.) The two can run in either
order: the knos_pay build does not need the knos_oidc one, and the other way round.

**Gated from the push that adds program.yml's `v3-build` job.** That job runs `scripts/build_sbf.sh v3 deploy` on a
GitHub-hosted runner with the toolchain above (both archives held to their sha256), fails unless the builds are the
table's bytes and the two buffers hold them (`V3_EXPECT: deploy/upgrade-0335/HASHES-v3.txt`), and the `gate` job has
GitHub sign `gate:<program>:<hash>` for both; the relay records them in examples/upgrade_gate. Once
`python examples/upgrade_gate/adopt.py check --gate 2DfVEuBMWvvh3kXZaQwk2SoszJsoV1PTiK1VGCkB55HW --program <program id> --buffer <buffer>`
exits 0 for a buffer, propose it WITHOUT `--ungated`; the propose line then names the commit and run GitHub built it in.
A proposal already made with `--ungated` carries the same instruction on chain (the flag is only the script's own
check before it sends): once the record exists, `adopt.py check --multisig 9HcsMEo2o6zZu9t1kbFWpnyKn7hiHaZYYFwNHZSpmWqK`
shows it gated, and it need not be made again.

## Do NOT propose these earlier buffers (superseded; all held by the vault)

| buffer | program | executable hash | why not |
|---|---|---|---|
| `Dfo5pYRLY8z9yvuXDQjJQtaoqJeL7Atso8zhWy9Ehkfj` | knos_pay (0.3.34, deploy/upgrade-0334) | `9ae13fb9…` | superseded by `C7MrKvNU2yxMG5RJqzCkCDGowe5T1R69j3LXz3Qj1VdA`: the same 0.3.34 code without the Knos claim home |
| `4sqFJdjHYi44jQQwyweumbFU9vrWGfWZ2bWKQYKgaKRF` | knos_pay (0.3.29) | `95fa02b2…` | superseded twice |
| `7Rcga9yCjsBt9nFmB6LXq9z6c8dwXpvvMjMpe9ZwytCt` | knos_pay | `69ec05b8…` | proposal 2, status `replaced` in web/upgrades.json |
| `3xBgKGynRGRLCs2ShYsyAdNucLbE3KjvMFnKFJoiPiyr` | knos_oidc (0.3.30 one-transaction RSA) | `d565487f…` | superseded by `dJA4mokfAqG7eTKUrD1MawKbWPJrzjc72qehpujiy6V`: the same code without the Knos rotate home |
| `5LogeNBTiydReTi8ksbA7CAYJacs6wBL7t8xiWLtpzaD` | knos_oidc (0.3.29) | `14dfede2…` | superseded twice |
| `DS34bn3fzu7F6ngzXTDjBwJQpqXAFm4QUNLQ2Vo2FgD9` | knos_oidc | `a9dd1d07…` | proposal 1, status `replaced` in web/upgrades.json |

The knos_meter (`EpvdeEj3TSv4E2dSJBSmfD3UeR8bsGkqYtkTNFhUjoVe`, 0.3.30) and knos_passkey
(`CLfjbizPnSwLRrkCTHFtHhBdLkuoFCoP96VdKnU2gU9w`) buffers are not touched by this upgrade. Executable hashes above are
read from each buffer on devnet (`solana program dump` + sha256 of the bytes without trailing zeros).

## 3. Wait the time lock, then execute

Each proposal waits 691,200 seconds (8 days) after its approval. `node scripts/governance.mjs cancel upgrade <index>`
withdraws one. After the lock:

    node scripts/governance.mjs upgrade execute <knos_oidc index> --expect-hash 925c76f051f9c28f617dc18352fcdab6127b2d23b164eb87fcab282e02bbe968
    node scripts/governance.mjs upgrade execute <knos_pay index>  --expect-hash e01605411369b40b9e6fd28595d0254f06357fbf7f5c887eef207f8d5b68ad3a

Then `solana-verify get-program-hash -u devnet FkwZdsYCmzicJMtHLTkPK76bYNVG4WNwkWJBiVWNtF3W` prints `925c76f051f9c28f617dc18352fcdab6127b2d23b164eb87fcab282e02bbe968` and
`solana-verify get-program-hash -u devnet 5y7iWJ1VAMJjnnWbbdo2a2PsWJEwTExSNpzrvQSEnS8k` prints `e01605411369b40b9e6fd28595d0254f06357fbf7f5c887eef207f8d5b68ad3a`. Update
programs-v2/README.md, web/upgrades.json (`python scripts/upgrade_feed.py`) and docs/reference/PROVENANCE.md with them.
Everything deploy/upgrade-0334/STEPS.md step 4 lists for knos_pay (Confidential Space and ORCID keys, the ORCID client)
applies to this build too.

## 4. After execution: the callers move (not before)

Before the upgrade executes, a caller in Knos attests nothing and binds nothing: the live programs refuse the Knos home
(tests/test_two_homes_rotate.py and tests/test_two_homes_claim.py run the builds before this change and show it).

The branch `oidc-rotate` and its tags must be in drexthealpha/Knos first (CUTOVER-0331.md section 2 step 1):
`git ls-remote origin refs/tags/oidc-rotate-212f9eb5f584` names
212f9eb5f584eb6f8cd2d6673878132fc0011e27.

### 4a. The rotate caller, in Knos `main`, only after 5 Dec 2026 (Colosseum guard: `main` and tag v0.3.28 stay as they are until then)

Replace `.github/workflows/keys.yml` (which calls the old home at 6ddf031b) with `.github/workflows/oidc-rotate.yml`,
in one commit, so that one schedule runs:

```yaml
# .github/workflows/oidc-rotate.yml: the rotate workflow from its home in Knos (branch oidc-rotate), at the commit
# knos-oidc pins as ROTATE_SHA2. It reads the issuers' key sets and posts one GitHub-signed token per key for a relayer
# to carry to knos-oidc (RegisterKey, Refresh). By its schedule or by hand, in this repository (an attester's).
name: issuer keys

on:
  schedule:
    - cron: "11 5 * * *"
  workflow_dispatch:
    inputs:
      issuer:
        description: "https URL of the issuer, or empty for GitHub and GitLab"
        required: false
        type: string
        default: ""

permissions: {}

jobs:
  keys:
    permissions:
      id-token: write
      issues: write
    uses: drexthealpha/Knos/.github/workflows/rotate.yml@212f9eb5f584eb6f8cd2d6673878132fc0011e27
    with:
      issuer: ${{ inputs.issuer || '' }}
```

In the same commit the tests that pin the old caller follow it: `tests/test_settle_fixtures.py`
(`test_the_rotate_pin_is_one_commit_everywhere` reads keys.yml and the first deployment's ROTATE_SHA: the first
deployment takes only the old home, so keep the old `keys.yml` as long as its keys must be refreshed, or change that
test to read the new file against `rotate_sha2` and the second deployment), and `tests/test_workflows2.py` (the
`keys.yml` lines). Then start the workflow by hand once and watch its tokens reach knos-oidc (`knos status` lists every
key and its expiry): a key refreshed by that run is the proof the new home works.

### 4b. The claim callers, on branch knos-0.3.x, after the upgrade executes

Every place that writes a claim caller changes one line, `drexthealpha/knos-oidc-rotate/` to `drexthealpha/Knos/`,
at the same commit:

| file | the `uses:` line after the change |
|---|---|
| `examples/knos-claim.yml` and its copy `src/knos/settle/knos-claim.yml` (byte for byte; `knos claim` commits it) | `uses: drexthealpha/Knos/.github/workflows/claim.yml@80e796d341f65060767939c4e65a38ede5fa1ac8` |
| `examples/knos-claim-org.yml` and `src/knos/settle/knos-claim-org.yml` | `uses: drexthealpha/Knos/.github/workflows/claim.yml@212f9eb5f584eb6f8cd2d6673878132fc0011e27` |
| `web/payee.js` (the caller the payee page shows) | `uses: drexthealpha/Knos/.github/workflows/claim.yml@80e796d341f65060767939c4e65a38ede5fa1ac8` |

`templates/knos-claim/` and `templates/knos-claim-org/` hold no `uses:` line (only README.md and LICENSE): nothing to
change there.

The tests that pin the old caller change with them: `tests/test_workflows2.py`
(`test_the_claim_caller_names_the_pinned_commit_and_takes_the_address_from_the_right_place`, `ROTATE`),
`tests/test_small_repos.py`, `tests/test_money_cli.py` (the pinned-caller fixtures), `tests/web/payee.mjs`. `knos claim`
(`src/knos/claim.py`) matches `claim.yml@<commit>` and works with either home, so a person whose knos-claim still calls
the old home keeps working: Bind takes both. Existing knos-claim repositories need no change.

knos-oidc-rotate itself stays (CUTOVER-0331.md section 2 step 5): the first deployment takes only its path, and every
existing knos-claim repository calls it.
