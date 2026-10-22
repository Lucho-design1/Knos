<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Audit before 0.3.29: sBPF versions, Sibyl, devnet feature gates

**In plain words.** Before 0.3.29 changes the programs, this page records three facts as they stood on 13 Oct 2026:
which sBPF version every Knos program binary is, whether the memory engine is still Sibyl and what its test proves,
and which Solana features devnet has switched on. Every value below was read by a command named beside it; nothing
here is estimated. It was read from commit `99cc4e3e` (v0.3.28) and from devnet; no transaction was sent.

## 1. sBPF version of every program binary

How it was read: byte 18 (`e_machine`) and byte 48 (`e_flags`, 4 bytes, little-endian) of each ELF file. In the
sBPF loader `e_flags` is the sBPF version: 0 = v0, 1 = v1, 2 = v2, 3 = v3. `e_machine` 263 is `EM_SBPF`.
Deployed binaries were read with `solana program dump -u devnet <program id>` (read-only).

| program | file | e_machine | e_flags | sBPF version | commit (added / last changed) | reason given |
|---|---|---|---|---|---|---|
| knos_oidc (deployed, 2nd deployment) | devnet `FkwZdsYCmzicJMtHLTkPK76bYNVG4WNwkWJBiVWNtF3W` (last deployed slot 509118532) | 263 | 0x0 | v0 | built from `f03ec515d` (PROVENANCE.md) | none: default target |
| knos_pay (deployed, 2nd) | devnet `5y7iWJ1VAMJjnnWbbdo2a2PsWJEwTExSNpzrvQSEnS8k` (slot 509118717) | 263 | 0x0 | v0 | built from `f8bcd9d51` | none: default target |
| knos_meter (deployed, 2nd) | devnet `FUMKkcE95x2kZUj1zZTCbgcYBmJ3WXPHL8pyA8J6anX` (slot 508314467) | 263 | 0x0 | v0 | built from `6eb81dd15` | none: default target |
| knos_passkey (deployed, 2nd) | devnet `FQPX9i5kQxLYKZyyPgM2fVK9am3w1LSk1Cuoer1sSY85` (slot 508314496) | 263 | 0x0 | v0 | built from `6eb81dd15` | none: default target |
| knos_oidc (1st deployment, no upgrade authority) | devnet `vpWym9azbPU5f2PH2a6n8c4RfmsyUeW2dMuWr1DSHcE` (slot 506592324) | 263 | 0x0 | v0 | `programs/` | none |
| knos_pay (1st deployment, no upgrade authority) | devnet `9UzPFbh2A4e4sEPgngKG523FfYLnQ3qPfFVfFTTAdfDi` (slot 506592380) | 263 | 0x0 | v0 | `programs/` | none |
| knos_oidc | tests/fixtures/knos_oidc_v2_real.so | 263 | 0x0 | v0 | `3bf54a102` / `f03ec515d` | none |
| knos_oidc | tests/fixtures/knos_oidc_v2_test.so | 263 | 0x0 | v0 | `3bf54a102` / `f03ec515d` | none |
| knos_oidc (1st) | tests/fixtures/knos_oidc_test.so | 263 | 0x0 | v0 | `0e76b28d1` / `0e76b28d1` | none |
| knos_pay | tests/fixtures/knos_pay_v2_test.so | 263 | 0x0 | v0 | `3bf54a102` / `f8bcd9d51` | none |
| knos_pay | tests/fixtures/knos_pay_v2_nodevnet.so | 263 | 0x0 | v0 | `3bf54a102` / `f8bcd9d51` | none |
| knos_pay | tests/fixtures/live/knos_pay_v2_test.so | 263 | 0x0 | v0 | `f8bcd9d51` / `f8bcd9d51` | none |
| knos_pay (1st) | tests/fixtures/knos_pay_test.so, knos_pay_nodevnet.so | 263 | 0x0 | v0 | `0e76b28d1` / `0e76b28d1` | none |
| knos_meter | tests/fixtures/knos_meter_test.so | 263 | 0x0 | v0 | `567fd12ca` / `6eb81dd15` | none |
| knos_passkey | tests/fixtures/knos_passkey_v2_real.so | 263 | 0x0 | v0 | `567fd12ca` / `6eb81dd15` | none |
| examples and gates | tests/fixtures/{cpi_fund,workflow_vault,upgrade_gate,reader_template}_v2_real.so, oidc_gate_test.so | 263 | 0x0 | v0 | `567fd12ca`..`f03ec515d` | none |

**Build commands and toolchain (as committed).**
- `scripts/build_programs_v2.sh` and `scripts/build_programs.sh` run `cargo build-sbf [--features testkeys]` with no
  `--arch` flag. `cargo-build-sbf --help` (2.3.13) says `--arch <arch> ... [default: v0] [possible values: v0, v1, v2, v3]`.
  So every build is v0 because the flag was never given.
- The deployed binaries are `solana-verify build ... --base-image solanafoundation/solana-verifiable-build:2.3.11`
  (`.github/workflows/program.yml`, `VERIFY_IMAGE`; pinned in commit `c2ee8458c`, 2 Oct 2026, "pin
  solana-verifiable-build 2.3.11 (rustc 1.84)"). Also no `--arch`.
- CI installs agave `SOLANA_VERSION: v2.3.13`, unchanged since program.yml was added in `4b8cd65a6` (1 Oct 2026).
- Crates: `solana-program = "=2.2.1"`, `rust-version = "1.84"` in all four `programs-v2/*/Cargo.toml`; no Anchor.
- The build machine used for this audit (13 Oct): solana-cli 2.3.13, cargo-build-sbf 2.3.13, platform-tools v1.48.
  docs/reference/BENCH.md names an earlier test build "made by cargo build-sbf 3.0.0 (platform-tools v1.51)"; its
  output is the same v0 (e_flags 0x0 in the committed fixtures).

**The downgrade the founder remembers: not found.** Searched, with no match:
- every commit message on every branch and tag of drexthealpha/Knos (236 commits locally, plus all 17 remote heads
  fetched): `git log --all -i -E --grep='sbpf|sbf.?v[0-9]|--arch|v3 target|downgrad'`;
- every diff: `git log --all -S` for `sbpfv3`, `sbpfv2`, `sbpf-v3`, `sbpf-v2`, `--arch`, `v3.sbf`, `sbpfv`, `SBPF`,
  `arch=v3`, `sbpf_version`, `enable_sbpf`, `e_flags`, and `-G 'sbpf|--arch'`. The one `-G` hit, `6eb81dd15`, only adds
  the `solana-sbpf` crate to a Cargo.lock (a LiteSVM dependency of the test crate), not a build target;
- GitHub code and commit search `sbpf user:drexthealpha` and `"--arch" build-sbf user:drexthealpha`: 0 results;
- the maintainer's local working copies and build folders (keys and build output excluded): no `sbpfv<n>`,
  `sbpf-v<n>`, `--arch v<n>` or `SBPFv<n>` text.

**Plainly: every Knos binary was built as sBPF v0, and no commit ever targeted sBPF v3** (nor v1 or v2). Every
binary that was committed or is live on devnet is v0. A v3 build made outside this repository, or a devnet deployment overwritten
before the current one, cannot be ruled out from here (`solana program dump` returns only the current program data).
Note: devnet activated SBPFv3 deployment only at slot 461808000 (epoch 1069, section 3), so a v3 program could not
have been deployed to devnet before that slot.

## 2. Sibyl is still the memory engine

Command: `PYTHONPATH=src python -m pytest -q -p no:cacheprovider tests/test_sibyl_is_load_bearing.py`
at `99cc4e3e`: **24 passed** in 46.42 s (13 Oct 2026). The engine is `sibyl-memory-client` 0.8.1 (installed; the
dependency in pyproject.toml is `>=0.8.1`); `src/knos/proof/history.py` (1,630 lines) wraps it as `SibylStore`
(`for_repo` uses Sibyl's shared `~/.sibyl-memory/memory.db`, `local(dir)` uses `<dir>/sibyl.db`).

What the test proves: - The Stop hook blocks a false "done" only because of a rule Sibyl learned; the same hook with
`NullStore` allows it. - What was learned lives only in Sibyl's own database (entities, journal events); deleting it
removes the behaviour, a corrupt file raises instead of being papered over, and with the package removed `SibylStore`
raises ImportError. - Sibyl's free-tier cap is enforced by Sibyl's own gate (`CapExceededError`), not bypassed. - The
GitHub judge refuses an agent's second pull request because of what Sibyl kept from the first; lessons that travel in
the `knos-memory` issue decide nothing until loaded into a Sibyl store. - Refusals are COLD journal events, the
running count is a HOT state document, rules are WARM entities; owed checks, the per-host answers (every host in
tests/_host_events.py) and the funding-reply terms line all change when the store is deleted or edited.

Gaps (true at `99cc4e3e`): - **Memory is optional at run time.** If `sibyl_memory_client` is missing or the store fails to
open, the hook falls back to `NullStore` and still runs (`src/knos/proof/hook.py` lines 131-135; also preflight.py,
recall.py, proof/cli.py).

The test asserts this fallback; it is by design, but it means "load-bearing" is "decisions change with Sibyl", not "Knos
refuses to run without Sibyl". - **No tamper evidence.** A hand edit of Sibyl's journal changes the outcome and nothing
detects it (the test `..._an_edited_journal_changes_the_outcome` asserts exactly this). There is no hash chain, Merkle
root or anchor of the journal.

Phase 6 (Knos Record) is where this would be closed. - The test exercises local SQLite stores with stubbed check runners;
it does not touch chain payments. The on-chain programs (knos_pay etc.) do not read Sibyl.

## 3. Feature gates on devnet

How it was read: `getMultipleAccounts` on `https://api.devnet.solana.com` for each feature id, context slot 510670272
(epoch 1182), 13 Oct 2026 15:27 UTC. A feature account's data is `Option<u64>` (the activation slot); no account
means the feature is not active. Devnet's epoch schedule is 432000 slots per epoch with no warmup, so epoch = slot /
432000.

`solana feature status` from solana-cli 2.3.13 cannot be used for the newer ids: it answers `Unknown feature` (it
only knows its own list), and several ids changed since 2.3.13. To repeat it, send `getMultipleAccounts` with the ids
below and `{"encoding": "base64"}`: byte 0 is 1 when active, and bytes 1 to 8 are the activation slot
(little-endian).

Ids are from agave `feature-set/src/lib.rs` at commit `c8db44f13afd63c64c4d98273eda4ae918dde3be` (the last commit
touching that file on master as of 13 Oct 2026); links below are permalinks to that file.
SIMD texts: github.com/solana-foundation/solana-improvement-documents, `proposals/`.

| feature | SIMD | id | devnet status | source |
|---|---|---|---|---|
| big_mod_exp syscall | SIMD-0529 (agave's description: "big_integer mod_exp syscall") | `expH2ppKPW2ANEdEmAjfhSEcnBQJfmoX4FjuNpe9ttg` | **inactive** (no account) | [agave L911](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L911), [SIMD-0529](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0529-big-integer-modexp-syscall.md) (status Idea) |
| big_mod_exp, older id (solana-cli 2.3.13) | none listed ("add big_mod_exp syscall #28503") | `EBq48m8irRKuE7ZnMTLvLg2UuGSqhe8s8oMqnmja1fJw` | **inactive** | `solana feature status -u devnet --display-all` (cli 2.3.13) |
| Larger transactions, 4096 bytes | SIMD-0296 | **id not found** | n/a | [SIMD-0296](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0296-larger-transactions.md) (status Review) has `feature: (fill in ... once accepted)`; agave feature-set has no SIMD-0296 entry; agave issue search for "SIMD-0296" finds only PR #6487 "Raise CPI Nesting Limit to 8" (closed, reverted by #7296), an unrelated use of the number |
| Transaction V1 (4096-byte transactions) | SIMD-0385 | `txv1aq4pp281K9um3tnPgkfX8UqtFT6wcVW3hNezGLL` | **active** since slot 492480000 (epoch 1140) | [agave L1494, L2611](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1494), [SIMD-0385](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0385-transaction-v1.md) (its table: transaction size 4096 vs 1232) |
| alt_bn128 G2 syscalls | SIMD-0302 | `bn1hKNURMGQaQoEVxahcEAcqiX3NwRs6hgKKNSLeKxH` | **active** since slot 457056000 (epoch 1058) | [agave L1395](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1395), [SIMD-0302](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0302-bn254-g2-syscalls.md) |
| BLS12-381 syscalls | SIMD-0388 | `b1sgUiJ3qu7hYm3tNDyyqZNQd6gLGJmJppnLNa93PCQ` | **active** since slot 457488000 (epoch 1059) | [agave L1407](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1407), [SIMD-0388](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0388-bls12-381-syscalls.md) |
| Poseidon: enforce input padding/length | SIMD-0359 | `poUdAqRXXsNmfqAZ6UqpjbeYgwBygbfQLEvWSqVhSnb` | **active** since slot 438048000 (epoch 1014) | [agave L1363](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1363), [SIMD-0359](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0359-poseidon-enforce-input-length.md) |
| Poseidon syscall itself | none listed | `FL9RsQA6TVUoh5xJQ9d936RHSebA1NLQqe3Zv9sXZRpr` | **active** since slot 310608000 (epoch 719) | [agave L1011](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1011) |
| secp256r1 precompile | SIMD-0075 | `srremy31J5Y25FrAApwVb9kZcfXbusYMMsvTK9aWv5q` | **active** since slot 380592000 (epoch 881) | [agave L1223](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1223), [SIMD-0075](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0075-precompile-for-secp256r1-sigverify.md) (feature line gives the same id) |
| Loader v4 | SIMD-0167 | `LoaderV4WasAbandoned11111111111111111111111` | **inactive** (no account; the id itself says the feature was abandoned) | [agave L1023](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1023) |
| Loader v4, older id (solana-cli 2.3.13) | SIMD-0167 | `2aQJYqER2aKyb3cZw22v4SL2xMX7vwXBRWfvS4pTrtED` | **inactive** | cli 2.3.13 feature list |
| Disable deployment of SBPF v0, v1, v2 | SIMD-0500 | `B8JJXCy5amZyWG9r7EnUYLwzXSXTxG7GZ1qZ1qggo83g` | **inactive** (no account): v0 deploys and upgrades still work on devnet today | [agave L1211, L2345](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1211), [SIMD-0500](https://github.com/solana-foundation/solana-improvement-documents/blob/main/proposals/0500-disable-deployment-of-sbpf-v0-v1-v2.md) (status Idea, `feature: TBD`) |
| SBPF v3 deployment and execution | SIMD-0178, 0189, 0377 | `5cC3foj77CWun58pC51ebHFUWavHWKarWyR5UUik7dnC` | **active** since slot 461808000 (epoch 1069) | [agave L1207](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1207) |
| SBPF v3, older id (solana-cli 2.3.13) | SIMD-0178, 0179, 0189 | `C8XZNs1bfzaiT3YDeXZJ7G5swQWQv7tVzDnCxtHvnSpw` | **inactive** | cli 2.3.13 feature list |
| SBPF v1 / v2 deployment and execution | SIMD-0166 / 0173, 0174 | `JE86WkYvTrzW8HgNmrHY7dFYpCmSptUpKupbo2AdQ9cG` / `F6UVKh1ujTEFK3en2SyAL3cdVnqko1FVEXWhmdLRu6WP` | **active** since slot 389664000 (epoch 902) / 396576000 (epoch 918) | [agave L1199-L1205](https://github.com/anza-xyz/agave/blob/c8db44f13afd63c64c4d98273eda4ae918dde3be/feature-set/src/lib.rs#L1199) |

What follows for 0.3.29 (from the table only): - No big_mod_exp on devnet: the one-transaction RSA verify must be
done in the program's own arithmetic. - Transactions up to 4096 bytes are available on devnet through Transaction V1
(SIMD-0385), not through a SIMD-0296 feature. - SBPF v3 can be deployed on devnet (since epoch 1069).

SIMD-0500 is not active yet, so today's v0 binaries can still be upgraded; once it activates they cannot be
redeployed as v0. - secp256r1, alt_bn128 G2, BLS12-381 and Poseidon (with padding enforcement) are active on devnet.
- Mainnet was not queried.
