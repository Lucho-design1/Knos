# Knos on today's Solana: sBPF v3, one-transaction verification, v1 transactions (v0.3.29)

**In plain words.** Every Knos program ever built was built for the oldest program format, sBPF v0 (no commit ever
targeted another; the AUDIT page has the history). This release builds the four programs for sBPF v3, which devnet runs
today and which future upgrades will require. A build for sBPF v2 also checks a GitHub token's RSA signature in ONE
transaction instead of two (measured on devnet: 882,519 compute units); today's v3 cannot, for lack of a 128-bit
multiply, so it keeps two. The new builds are written to devnet and handed to the
upgrade multisig; they replace the live programs only when the founder's Squads proposal passes its 8-day time lock.
Nothing on this page has replaced a live program yet.

## 1. What devnet runs (13 Oct 2026)

Read from devnet's feature accounts; the AUDIT table in the release notes has the slots and ids.

| feature | on devnet | what Knos does with it |
|---|---|---|
| sBPF v3 deployment and execution (`5cC3fo…`) | active | the four programs are built for v3 (`scripts/build_sbf.sh v3`) |
| sBPF v2 (`F6UVKh…`) | active | its PQR instructions (64 x 64 -> 128-bit product) make one-transaction RSA possible; the v3 of Agave 4.4 lacks them |
| v1 transactions, 4,096 bytes (SIMD-0385, `txv1aq…`) | active | a token and its verification in one transaction (section 4) |
| secp256r1 precompile (SIMD-0075) | active | ES256 tokens (section 5) |
| `big_mod_exp` syscall | **not active** (no feature account) | not used by any deployed build; a build with the crate feature `big_mod_exp` exists for a cluster that has it |
| SIMD-0500: no new deployments of sBPF v0, v1, v2 (`B8JJXC…`) | not active yet | the reason the v3 buffers are prepared now (section 7) |
| Agave version | 4.4.0-beta.0 (`solana cluster-version -u devnet`) | the local measurements use the same release |

## 2. Builds

`bash scripts/build_sbf.sh v3 deploy` builds the four programs with a pinned toolchain (cargo-build-sbf 4.4.0 from
the Agave 4.4.0-beta.0 release, platform-tools v1.57, `--locked`, file paths remapped so the bytes do not depend on where the checkout is) and
writes their hashes to [`deploy/upgrade-0329/HASHES-v3.txt`](../../deploy/upgrade-0329/HASHES-v3.txt). The ELF
header's `e_flags` is the sBPF version; the script refuses a file whose version is not the one asked for.
**Not the 2.3 toolchain.** An sBPF v3 file built by cargo-build-sbf 2.3.13 with platform-tools v1.48 (the toolchain
the repository used until now) does not load in Agave 4.4: `solana-test-validator` 4.4.0-beta.0 stops with "ELF
error: Failed to parse ELF file: invalid file header". The v3 format devnet activated (feature `5cC3fo…`) is a later
one than the 2.3 toolchain writes. So v3 needs the 4.4 toolchain. The v2 test build of the 2.3 toolchain loads in both
solders 0.29's LiteSVM and Agave 4.4.
The Python tests load `tests/fixtures/platform/knos_oidc_v2_test.so`, the test build (`--features testkeys`) for
sBPF v2, built with the repository's pinned 2.3 toolchain (`cd programs-v2/knos_oidc && cargo build-sbf --arch v2
--features testkeys`): LiteSVM as solders 0.29.0 ships cannot load an sBPF v3 file ("invalid file header"),
so v3 is measured in `solana-test-validator` 4.4.0-beta.0.

The verified (docker) build is `solana-verify build "$PWD" --workspace-path "$PWD/programs-v2" --library-name <name>
--arch v3 --base-image <image>`. This machine has no docker, so that build was not run here: the members compare the
buffers with their own rebuild (STEPS.md says how).

The v3 deploy builds (cargo-build-sbf 4.4.0, platform-tools v1.57; `deploy/upgrade-0329/HASHES-v3.txt`), each smaller
than the program data account it would replace on devnet (oidc 279,360, pay 408,280, meter 317,600, passkey 214,176
bytes), so no ExtendProgram is needed:

| program | e_flags (sBPF) | bytes | executable hash (`solana-verify get-executable-hash`) |
|---|---|---|---|
| knos_oidc | 3 | 169,280 | `14dfede29c059c4ad3cf8eb7ee3f7754c1d21a21838f0f59e2bb83a932e067e3` |
| knos_pay | 3 | 362,512 | `95fa02b2b16e6336a5a9cd8cb1fe1a8246c55a2176e8a875b7099d49b86d6fb5` |
| knos_meter | 3 | 158,368 | `faaaa6952905ee0266868fd6817f35ebf898136b87b00fbd7bce35cdb2c50cbe` |
| knos_passkey | 3 | 108,232 | `d5a5db160eab9fbfdd70712f14898b06daeb1b068eaa1f442f82fe492e5b1c73` |

These are built from this release's source with the PLATFORM changes uncommitted; the hashes change if anything in
programs-v2 changes before the commit. Rebuild at the release commit and compare before proposing (STEPS.md, step 0).
`deploy/upgrade-0329/HASHES-v3-agave23-REFUSED.txt` keeps the hashes of the v3 builds of the 2.3 toolchain, which
Agave 4.4 refuses, as evidence.

## 3. One-transaction RS256 verification

knos-oidc computes s^65537 mod n (16 squarings and one product) in Montgomery form. The v0 build does it on 32-bit
limbs (`rsa.rs`): a 2048-bit squaring is 64 x 64 limb products plus the reduction, and the whole verification costs
more than one transaction's 1,400,000 compute units, so the client sends Step(8), Step(8). The v2 build does the
same arithmetic on 64-bit limbs (`rsa64.rs`, chosen by `build.rs` for an sBPF v2 target, `modexp.rs`): the PQR
instructions make each 64 x 64 -> 128-bit product two instructions, and a squaring is 32 x 32 limb products, a quarter
of the multiplications. One Step(16) then does everything in one transaction. The token account is unchanged, and the
running power is the same bytes in both arithmetics, so a token stepped halfway under one build finishes under the
other (an upgrade between two Steps changes nothing; `tests/test_platform_verify.py`).

**sBPF v3 cannot do this today.** The v3 that Agave 4.4 runs (SIMD-0178, SIMD-0189, SIMD-0377) has no high-half
multiply: a v3 build of platform-tools v1.57 holds `mul64` and no `uhmul64` (`llvm-objdump -d`), where the v2 build holds
21 `uhmul64`. So on v3 a 128-bit product is emulated, and 64-bit limbs are slower than 32-bit ones: measured below, a
v3 build with 64-bit limbs took 1,027,779 + 1,086,730 compute units for Step(8), Step(8) and ran out on Step(16).
`build.rs` therefore uses 64-bit limbs for v2 only; the v3 builds keep the 32-bit arithmetic and the two-step plan.
One-transaction verification on devnet today needs the v2 build of knos_oidc (a founder decision: section 7).

`big_mod_exp` is not active on devnet, so no deployed build uses it. The crate feature `big_mod_exp` does the power
in one syscall for a cluster where it is active; a program that names an inactive syscall does not load.

**Measured** in LiteSVM (solders 0.29.0) with the test builds (`--features testkeys`) and a GitHub-shaped token signed
by the tests' seed-derived 2048-bit key (synthetic tokens, real arithmetic; `pytest -s tests/test_platform_verify.py`
prints every figure). Compute units per transaction; a transaction may use 1,400,000.

| build | plan | 1,922-byte token | 3,500 bytes | 8,192 bytes (the most the program takes) |
|---|---|---|---|---|
| sBPF v0, 32-bit limbs (what devnet runs) | Step(8), Step(8) | 762,618 + 828,096 = 1,590,714 in two transactions | | |
| sBPF v0, 32-bit limbs | Step(16) | refused: out of compute units | | |
| sBPF v2, 64-bit limbs | Step(8), Step(8) | 425,513 + 491,167 | | |
| sBPF v2, 64-bit limbs | **Step(16), one transaction** | **881,617** | 941,261 | 1,117,916 |
| sBPF v2, 64-bit limbs | Write (whole token) + Step(16) in ONE v1 transaction of 2,322 bytes | **893,664** | | |

A 4096-bit key (GitLab's) under the v2 build: Step(4) four times, at most 971,533 compute units a transaction for a
2,379-byte token and 1,193,424 for 8,191 bytes: four transactions where the v0 build needs six. A tampered signature is
refused by the one-step path (error 70; 65 when the changed signature is not below the modulus).

**Measured on devnet** (13 Oct 2026, Agave 4.4.0-beta.0): the same sBPF v2 test build deployed at a program id of
our own, `2V9M2NyfQGGUxpdSXiVjgUfpTrdy4xgkZ7KowBX753j9` (deploy `5Zw8aGyr…`; upgrade authority the PLATFORM wallet
`42agkcTx…`; a TEST build: it trusts only the tests' seed keys, and it is no Knos program). Compute units as the
cluster reports them (`getTransaction` `computeUnitsConsumed`), 1,921-byte token:

| what | transaction | compute units |
|---|---|---|
| Step(8), then Step(8) (the old plan, under the v2 build) | `RKfE4QjG…`, `3HxyvjzJ…` | 427,192 + 492,140 |
| **Step(16): the whole verification in ONE transaction** | `44AdiYqa…` | **882,519** |
| **Write (whole token) + Step(16) in ONE v1 transaction of 2,279 bytes** | `3N3TyGNC…` | **889,651** |

Full signatures: RegisterKey `2dHLQhq4noXF7q5VkGwpTdUs1nd7HAMnq8hLHfsJRXrDLhopCibVc4SBFAxajhT8EEq34tVHGPJ7KiVcHAVaKR1F`,
KeyParams `4idQiQZmHtM7Rp8zxmWTgZfWgEi4aPNynsM7BfCVcPoLtmESZ5fSz1JHrE9SwkZmPXHhU415u4Qm2vjj9ANRm8Uh`, Step(8)
`RKfE4QjGYHES2keLNJAH6CiX5h4jr8Cv6HCrBLbuVFkyd4CGc2vv39fznarYRPiUbvt8GYvtFJET2y9rozj5B8d` and
`3HxyvjzJWBZGoyRtRGUezLRa5k8TWKdjwHssUWfr42WFwEkCicdvMuMYeseyo1cpJQGNuSSzqZZRHwGvLU23rgq7`, Step(16)
`44AdiYqamWoJ5ak2xa2orGu1uRpJUwuh2hujMdWxfVVTD2mS1EaATWwAnygvRXZsNQgN9SH7F1Vm6z3v99BpR3X6`, v1
`3N3TyGNCgdTQ8MBcFadxiMUiCy8F3CiFAdE44wFLuD3kXGn1X3BCojMzZFf1QGMRQnAskEnhNC3JAGeUNZ3cxwDs`, deploy
`5Zw8aGyrYY5ukXWnjBb1xL3V9C5cGhK2RWQ2Rs6Ajv9Nxm1i1ieDpZPv4TDgKjKAo5i7kb7E9rnRcEpJRxSTSZ87`.

**All three formats side by side** in `solana-test-validator` 4.4.0-beta.0 (the release devnet runs, every feature
active, including SIMD-0500 and SIMD-0385), each test build at its own program id, the same 1,921-byte token
(`v0329/agents/PLATFORM/val.sh` drives `val_cu.py`; compute units from `getTransaction`):

| build | Step(8) + Step(8) | Step(16), one transaction | Write + Step(16), one v1 transaction |
|---|---|---|---|
| sBPF v0, 32-bit limbs (today) | 761,805 + 826,794 | out of compute units (1,399,850 consumed) | out of compute units |
| sBPF v2, 64-bit limbs | 421,797 + 488,638 | **881,415** | **896,314** (2,279 bytes) |
| sBPF v3, 32-bit limbs (the v3 deploy builds) | 719,805 + 781,472 | out of compute units | out of compute units |
| sBPF v3, 64-bit limbs (first attempt, discarded) | 1,027,779 + 1,086,730 | out of compute units | out of compute units |

So: **before** 761,637 + 826,670 = 1,588,307 compute units in two transactions (LiteSVM, today's v0 test build,
1,893-byte token; 761,805 + 826,794 in the validator); **after**, with the v2 build, 882,519 in ONE transaction on
devnet (`44AdiYqa…` above). The v3 build is about 5% cheaper than v0 and still needs two transactions.

The client keeps the old path: `KNOS_OIDC_VERIFY=two` (the default until the upgrade has executed) sends Step(8),
Step(8), which every build takes; `one` sends Step(16); `auto` reads the deployed build's sBPF version
(`knos.platform.verify.plan`). Switch the default to `auto` once the upgrade proposal has executed.

## 4. v1 transactions (4,096 bytes)

`knos.chain` already sends v1 transactions (SIMD-0385) when a message is too big for 1,232 bytes, with the compute
limit and the priority fee (a lamport total) in the message. New here: `knos.platform.verify.one_transaction_ixs`
puts the whole token (one Write) and Step(16) in ONE v1 transaction. The chunked Write path stays for a cluster or an
endpoint that refuses v1 (`chain.v1_refused`), which the relay falls back to.

Measured in LiteSVM (`tests/test_platform_verify.py`): a 1,922-byte token written whole and verified by Step(16) in one
v1 transaction of 2,322 bytes, 893,664 compute units, under the sBPF v2 build. The same instructions weigh more than
1,232 bytes, so no legacy transaction can carry them.

## 5. ES256 (secp256r1 precompile)

knos-oidc's VerifyEs256 (instruction 15, `es256.rs`) already verifies ES256 tokens through the secp256r1 precompile
at top level: it reads the instruction before it from the instructions sysvar and checks that it is the precompile
over this token's signing input and this key. A legacy transaction leaves 780 bytes for the signing input.
`knos.platform.verify.es256_v1_ixs` sends the same two instructions in a v1 transaction, where the signing input can
be about 3,400 bytes or more (`tests/test_platform_es256.py`).

Measured in LiteSVM (`tests/test_platform_es256.py`), one v1 transaction each, under today's v0 test build and the v2
build: a 781-byte signing input (1,287-byte transaction) 40,183 and 41,013 compute units; 2,000 bytes (2,506) 75,320 and
78,870; 3,000 bytes (3,506) 104,082 and 107,132. A signature over other bytes is refused by the precompile: the
transaction does not run.

## 6. Per-claim accounts, rent, finality

- **Per-claim accounts.** A block gives each writable account at most 12,000,000 compute units (Agave's cost
  tracker). What one claim writes is its own: the token account `["tok", payer, sha256(token)]`, the order and its
  money `["ord", …]`, `["ov", order]`, the markers `["used", sha256(signature)]`, `["done", order, pr]`, `["q", …]`,
  `["as", …]`, `["hb", order]`. Shared by design: the fee account of a mint (orders are spread over several,
  `knos.settle.v2.fee_accounts`), the relayer that pays, and, for the 2.0 job instructions only, the per-mint vault
  `["vault", mint]`; orders do not use it. `knos.platform.claims.shared_writable` checks a set of instructions for
  accounts two claims both write (`tests/test_platform_claims.py`).
- **Rent.** Devnet's rent-exempt minimum is 5,080 lamports a byte including the 128-byte overhead (`solana rent`,
  13 Oct 2026), where it was 6,960: about 27% less, not the 90% of the proposal. The relay now asks the cluster
  (`getMinimumBalanceForRentExemption`, `Ledger.rent`) instead of using 6,960, so any cut is used the day it is live.
- **Finality.** `KNOS_COMMITMENT` = processed, confirmed (default) or finalized (`knos.platform.finality`). Every wait
  in `knos.chain` and the fan-out ledger uses it, so a faster finality (Alpenglow, SIMD-0326) needs no code change.

## 7. The upgrade

[`deploy/upgrade-0329/STEPS.md`](../../deploy/upgrade-0329/STEPS.md) is the founder's page: the buffers on devnet (written by
the PLATFORM wallet and handed to the upgrade vault `CKCrTB…`), how to check their bytes, the Squads proposal commands
(multisig `9HcsMEo2…`, time lock 691,200 s), and the decision between a v3 and a v2 knos_oidc. Nothing was proposed,
approved or executed, and no founder key signed anything. SIMD-0500 (`B8JJXC…`, not active on devnet on 13 Oct 2026)
will refuse v0, v1 and v2 deployments once active; programs already deployed keep running.

## 8. What is not done

- The verified (docker) build of the v3 programs: no docker on this machine. The program.yml change (`--arch v3`, a
  4.4 toolchain image) is a change outside PLATFORM's paths: REQ INTEG / founder.
- One-transaction RSA on sBPF v3: not possible with today's v3 (no 128-bit multiply); the 32-bit arithmetic could be made
  cheaper (Karatsuba, a 16-bit-limb product with 64-bit accumulation); not attempted.
- `big_mod_exp`: inactive on devnet; the crate feature is written but no build of it was compiled or run here.
- The relay still estimates the last Step's compute units with the two-step figures (`_LAST_STEP`); with
  `KNOS_OIDC_VERIFY=one` a Step(16) that does not fit beside other instructions is sent alone (the relay's existing
  fallback).
- Per-claim accounts: the 2.0 job instructions keep the per-mint vault (orders do not use it); moving jobs to per-job
  token accounts is a program change to the money path, left for a reviewed release.
