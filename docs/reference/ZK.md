# Prove a result without showing it (Knos ZK)

**In plain words.** A researcher says "my model gets at least 48 of the 64 hidden test cases right". The person who
holds the hidden test set should not have to publish it, or it stops being hidden. Knos ZK turns that sentence into a
small proof (256 bytes) that a Solana program checks.

The proof shows the score clears the bar. It shows nothing
else: not the test cases, not the answers. A payout can then require "a verified proof for this sealed test set at
this bar" before it pays.

Status: built and tested; devnet demo status in [Where it runs](#where-it-runs). The setup is a **toy** (see
[Limits](#limits)): devnet and tests only.

## What is proven

| | |
|---|---|
| private (never leaves the prover) | the N hidden labels and their salt; the N predictions of the submission and their salt |
| public input 0 `spec_hash` | MiMC commitment to the salted hidden labels, published before the work starts (the sealed spec) |
| public input 1 `pred_hash` | MiMC commitment to the salted predictions (the worker can check its own submission was used) |
| public input 2 `threshold` | the bar, below 2^16 |
| statement | count(pred_i == label_i) >= threshold |

The circuit is `zk/score_circuit/src/lib.rs` (arkworks 0.5, Groth16 over BN254). The commitment hash is MiMC-7 (91
rounds, the circomlib MultiMiMC7 chaining) with round constants from sha256, computed the same way in Rust and in
Python (`src/knos/zk/mimc.py`).

The salts are whole field elements: without one, a set of 64 labels from ten classes could still not be guessed, but
a small set could; the salt removes that.

The fixture (`zk/fixtures/score64`) is **SYNTHETIC**: 64 made-up labels from a fixed seed, a submission that gets 52
right, a bar of 48.

## The pieces

| piece | where | what it does |
|---|---|---|
| circuit + prover | `zk/score_circuit` | toy setup, one proof, writes the fixtures and the program's key (`src/vk.rs`) |
| on-chain verifier | `programs-v2/knos_zk` | groth16-solana 0.2.0 over Solana's alt_bn128 syscalls; `Verify` and `VerifyAndRecord` |
| CU measurement | `zk/litesvm_cu` | the built program in LiteSVM: real proof passes, tampered ones fail, CU written to `cu.json` |
| Python | `src/knos/zk` | pure-Python BN254 pairing and Groth16 check, MiMC, instructions, verdict account, payout rule |
| demo | `zk/devnet_demo.py` | verify, two tampered proofs sent past preflight, record, read back |
| tests | `tests/test_zk_*.py` | run from the small committed fixtures; no Rust, no network |

`knos_zk` is its own Cargo workspace: the four existing programs' build and lockfile are untouched.

### Instructions

```
0 Verify           0 | A_neg 64 | B 128 | C 64 | inputs 3x32           no accounts; fails unless the proof verifies
1 VerifyAndRecord  1 | bump | A_neg | B | C | inputs                   [payer, verdict PDA, system program]
  verdict PDA = ["verdict", spec_hash, pred_hash, threshold (2 bytes)]; 138 bytes:
  version | bump | spec_hash | pred_hash | threshold | slot u64 LE | recorder
```

Everything is big-endian; a G2 point is x.c1, x.c0, y.c1, y.c0 (the EIP-197 order the syscall reads). `A_neg` is the
proof's A with y replaced by q - y. Errors: 0 bad data, 1 proof refused, 2 wrong verdict address, 3 already recorded.

The payout rule (`knos.zk.client.payable`): the verdict account is owned by the program (only a verified proof
creates one), its `spec_hash` is the one the bounty sealed, its threshold is at least the bounty's bar, and (if named)
its `pred_hash` is the submission's.

## Measured

All on the build box (WSL2, 4 vCPU, 4 GB, shared), 13 Oct 2026, from `zk/fixtures/score64/meta.json` and `cu.json`.

| what | number |
|---|---|
| circuit size (N = 64) | 47,484 R1CS constraints, 3 public inputs |
| toy setup | 13.4 s |
| one proof | 9.6 s, peak memory about 390 MB (`/usr/bin/time -v`) |
| proof size | 256 bytes (A 64, B 128, C 64) + 96 bytes of public inputs |
| program binary `knos_zk.so` (cargo-build-sbf 2.3.13) | 99,640 bytes |
| devnet rent for that binary (`solana rent 99685`, 13 Oct) | 0.50705004 SOL |
| on-chain compute units | **not measured yet**: the LiteSVM run (`zk/litesvm_cu`) did not finish compiling inside the 10-minute build windows on the shared box; the command is in Where it runs |
| off-chain check in pure Python (`knos.zk.groth16.verify`) | about 0.6 s per proof (pytest durations) |


## Where it runs

| where | status |
|---|---|
| groth16-solana, native (Rust tests in `zk/score_circuit`) | real proof verifies; 9 tampered forms refused; below-the-bar unprovable (the crate's own Rust tests are green) |
| pure Python (`tests/test_zk_*.py`) | real proof verifies; tampered proofs and inputs refused |
| LiteSVM (`zk/litesvm_cu`) | written; see Measured for whether it ran |
| solana-test-validator | not run: on the shared box it did not reach RPC within a 10-minute window, twice |
| devnet | **waiting for devnet SOL.** The faucet refused every airdrop (`429: You've either reached your airdrop limit today or the airdrop faucet has run dry`). Program id reserved: `5M67Aqw1JHNSVrhFxCSzTmewdpysRKDtBKkTLrb192bk`; deployer `DqH5N34nJQydHFDMjiMyWjfSsQUnKrcjwDhcWdMgk5Cp` needs at least 1.1 devnet SOL (rent above, plus an equal deploy buffer that is refunded, plus fees). Then `zk/devnet_demo.py` sends the verify, the two tampered proofs and the record, and writes `zk/fixtures/score64/devnet.json`. |

To measure compute units anywhere with a Rust toolchain and the Solana CLI:

```
cargo-build-sbf --manifest-path programs-v2/knos_zk/Cargo.toml --sbf-out-dir out
KNOS_ZK_SO=out/knos_zk.so KNOS_ZK_CU_OUT=zk/fixtures/score64/cu.json   cargo test --release --manifest-path zk/litesvm_cu/Cargo.toml -- --nocapture
```


## Tampering

Each of these is refused (tests named in brackets):

| tampering | refused by |
|---|---|
| one bit flipped in A, B or C | groth16-solana native, Python, LiteSVM test (`tampered_proofs_and_inputs_are_refused`, `test_tampered_proof_is_refused`) |
| another spec hash, another submission hash, another bar | the pairing check: the proof is bound to its public inputs |
| claiming a lower bar than proven (47 instead of 48) | same; and the verdict account for 47 is never created |
| A sent without the negation the program expects | pairing fails |
| A and C swapped | pairing fails |
| a public input equal to the group order r | refused before the pairing (`PublicInputGreaterThanFieldSize`) |
| a proof from another circuit (N = 4) under this key | refused |
| a verdict recorded twice, or at an address that is not the PDA | errors 3 and 2 |
| an account not owned by the program, offered to a payout | `payable` says no |
| proving 53 when 52 are right | no witness satisfies the circuit; no proof exists |


## The zkVM route (SP1 / RISC Zero)

Asked for: a zkVM program (SP1 or RISC Zero) proving the score over private inputs, wrapped to Groth16 for the
verifier above. What happened on the build box (WSL2, 4 vCPU, 4 GB, shared with other jobs), time-boxed to 20 minutes:

- `sp1up` installed `cargo-prove sp1 (b8387fa 2026-10-10)` (release v6.9.0) on the second try; the first download
  failed with `curl: (56) Recv failure: Connection reset by peer` during a network outage. Its toolchain step printed
  `info: no toolchain installed for 'succinct'`, so no SP1 guest was built inside the time box.
- SP1's Groth16 wrap runs in Docker (or a native gnark build that needs Go). On this box: `docker: not found`, and
  no `go` on PATH. So an SP1 proof could not have been wrapped to BN254 Groth16 here even if the guest had proven.
- RISC Zero was not tried: its Groth16 wrap (`stark2snark`) has the same Docker need.

So the private-input proof is the arkworks Groth16 circuit above: it proves the same kind of statement (a checker
over private data, only commitments and the verdict public) and verifies with the same on-chain program.

A zkVM version is a later step on a machine with Docker and more memory; it would feed the same `knos_zk` verifier
once its proof is wrapped to Groth16 over BN254 (a new verifying key, a new `vk.rs`).

## Private funding (Token-2022 confidential transfers)

**Design only: not built, not tested.** Nothing in this patch moves tokens confidentially.

The design: a funder pays into a Token-2022 mint with the confidential-transfer extension and an **auditor ElGamal
key** held by Knos's compliance role, so amounts are hidden from the public but readable by the auditor; the payout
side stays the existing public USDC escrow (the non-private fallback, the default).

It would sit behind a flag (`private_funding: true` in the funding config) and fall back to the public path
whenever the flag is off or the cluster refuses the proof instructions.

Why it stops at design: confidential transfers need the ZK ElGamal proof program. On devnet its account
`ZkE1Gama1Proof11111111111111111111111111111` exists as an executable builtin (read 13 Oct 2026, slot 510690911), but
whether its instructions are enabled was not checked here, and the auditor key, the mint and who holds what are
founder decisions.

## Limits

- **Toy setup.** The proving and verifying keys come from a fixed seed (`TOY_SETUP_SEED` in the circuit). Anyone can
  recompute the setup's secret and forge a proof for any statement. A build that moves real money needs keys from a
  multi-party ceremony (for example a Powers-of-Tau phase 1 plus a circuit-specific phase 2), and then a new `vk.rs`
  and a new program build. That is a founder decision; nothing here claims a ceremony.
- **The holder of the hidden set proves.** The proof shows that whoever knows the labels behind `spec_hash` found
  the score; it does not show the labels are a fair test. Sealing the spec before the work (the referee's sealed
  hidden tests) is what makes `spec_hash` meaningful.
- **One circuit size.** The key fits N = 64 and three public inputs. Another N is another setup and another key.
- **Proofs are re-randomisable** (Groth16 is malleable). This does not matter here: the verdict account is keyed by
  the public inputs, not the proof bytes, so a second proof of the same statement records nothing new.
- No audit of this code exists.
