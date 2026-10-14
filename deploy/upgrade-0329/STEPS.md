# Upgrade 0.3.29: the four programs as sBPF v3, through the upgrade multisig

**For the founder.** Nothing here has been proposed, approved or executed. The PLATFORM agent wrote the new builds to
devnet buffers with its own wallet and handed each buffer to the upgrade vault. Only a proposal of multisig
`9HcsMEo2o6zZu9t1kbFWpnyKn7hiHaZYYFwNHZSpmWqK` that two members approve, executed after its 691,200-second (8-day) time
lock, can put a buffer's bytes into a program. No founder key signed anything to prepare this.

## Why now

- SIMD-0500 (feature `B8JJXCy5amZyWG9r7EnUYLwzXSXTxG7GZ1qZ1qggo83g`, "Disable deployment of SBPF v0, v1 and v2
  programs") is not active on devnet today. The founder's plan expects it with Agave 4.4, about November 2026
  (devnet already runs 4.4.0-beta.0, and the feature is active by default in its local validator). Once it is active,
  the loader refuses an upgrade to a v0, v1 or v2 build, and all four
  programs run v0 builds today. A proposal waits 8 days, so a v3 build must be proposed at least 8 days before the
  feature activates, or the next fix to any program cannot land until it is rebuilt as v3 and waits 8 more days.
- A v3 buffer is accepted before and after SIMD-0500. Programs already deployed keep running either way: SIMD-0500
  stops deployments, not execution.
- The v3 builds do NOT give one-transaction RSA: the sBPF v3 of Agave 4.4 has no 128-bit multiply, so knos_oidc v3
  still verifies a 2048-bit GitHub token in two transactions (719,805 + 781,472 compute units, about 5% less than the
  v0 build). One transaction needs the sBPF v2 build of knos_oidc (882,519 compute units on devnet). See the decision
  below.

## Founder decision: knos_oidc as v3 or as v2

- **v3 (recommended for safety):** all four programs v3. Every later upgrade stays possible after SIMD-0500. RSA stays
  two transactions until a later build makes the 32-bit arithmetic cheaper or the runtime gains a 128-bit multiply or
  `big_mod_exp`.
- **v2 for knos_oidc only:** one-transaction RSA now. v2 is deployable today, but SIMD-0500 also refuses v2
  deployments once active, so the NEXT upgrade of knos_oidc after activation must be a v3 build (two transactions
  again unless the arithmetic improves). The v2 buffer is listed below when the PLATFORM wallet had the SOL to write
  it. Its build: `cd programs-v2/knos_oidc && cargo build-sbf --arch v2 -- --locked` with cargo-build-sbf 2.3.13 and
  platform-tools v1.48 (the repository's pinned toolchain), 209,928 bytes, e_flags 2, executable hash
  `a4279958310110a28c0ed06da1b83f46939dfa34ea2ddf95384bc04d302100e4` (built in a local checkout without
  path remapping, so a rebuild elsewhere may differ in the paths of panic messages: rebuild from the same path, or
  write your own v2 buffer and compare its behaviour, not its hash).
  Deploy only ONE of the two knos_oidc buffers.

## What is in the buffers

The list is `BUFFERS.txt` beside this file: one line per buffer whose bytes were read back from devnet, equal to the
build, and whose authority is the vault (program, buffer address, executable hash, bytes, signature of the authority
change). It is written by `v0329/agents/PLATFORM/buffers.sh` (not part of the repository) as each buffer completes.
The builds and their executable hashes (`HASHES-v3.txt`; propose nothing whose hash differs):

| program | sBPF | bytes | executable hash |
|---|---|---|---|
| knos_oidc | v3 | 169,280 | `14dfede29c059c4ad3cf8eb7ee3f7754c1d21a21838f0f59e2bb83a932e067e3` |
| knos_pay | v3 | 362,512 | `95fa02b2b16e6336a5a9cd8cb1fe1a8246c55a2176e8a875b7099d49b86d6fb5` |
| knos_meter | v3 | 158,368 | `faaaa6952905ee0266868fd6817f35ebf898136b87b00fbd7bce35cdb2c50cbe` |
| knos_passkey | v3 | 108,232 | `d5a5db160eab9fbfdd70712f14898b06daeb1b068eaa1f442f82fe492e5b1c73` |
| knos_oidc (alternative, one-transaction RSA) | v2 | 209,928 | `a4279958310110a28c0ed06da1b83f46939dfa34ea2ddf95384bc04d302100e4` |

Buffer addresses chosen (keypairs in the PLATFORM wallet folder; a buffer appears in BUFFERS.txt only once complete and
handed to the vault): knos_oidc v3 `5LogeNBTiydReTi8ksbA7CAYJacs6wBL7t8xiWLtpzaD`, knos_pay v3
`4sqFJdjHYi44jQQwyweumbFU9vrWGfWZ2bWKQYKgaKRF`. If a buffer named here is not in BUFFERS.txt, it is not ready: do not
propose it.

Each listed buffer's authority is the upgrade vault `CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2` (checked with
`solana program show <buffer>`), so the wallet that wrote it can no longer change or close it. Each new build is
smaller than the program data account it replaces (279,360, 408,280, 317,600 and 214,176 bytes on devnet), so no
ExtendProgram is needed.

## Steps (in this order)

0. **Check the bytes yourself** (anyone can, no key). On a Linux file system, at the commit of this release:

       bash scripts/build_sbf.sh v3 deploy          # pinned toolchain; prints the hashes and writes HASHES-v3.txt
       solana program dump -u devnet <buffer> b.so && solana-verify get-executable-hash b.so

   The two hashes of each program must be equal. Also check `solana program show -u devnet <buffer>` says
   `Authority: CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2`. If a hash differs, do not propose that buffer: write a
   new buffer from your own build (`solana program write-buffer`, then `solana program set-buffer-authority <buffer>
   --new-buffer-authority CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2`) and use that address below.

1. **Decide gated or ungated** (founder decision). `scripts/governance.mjs upgrade propose` refuses a buffer that
   has no record at the upgrade gate (GitHub's runner building exactly these bytes in program.yml). program.yml builds
   sBPF v0 today. Either:
   - *gated (recommended)*: add `--arch v3` to program.yml's `cargo build-sbf` and `solana-verify build` lines (a
     change outside this patch: REQ INTEG), let it run on the release commit, and propose the bytes it records
     (`KNOS_CHANGES="knos_oidc knos_pay knos_meter knos_passkey" bash scripts/deploy_v2.sh --propose`), which writes its
     own buffers; or
   - *ungated*: propose these buffers with `--ungated`; the members then have only step 0 as evidence.

2. **Propose and approve** (two member keys; the founder holds all three today), one proposal per program:

       node scripts/governance.mjs upgrade propose knos_oidc    <knos_oidc buffer from BUFFERS.txt> --ungated --out oidc.json
       node scripts/governance.mjs upgrade propose knos_pay     <knos_pay buffer>  --ungated --out pay.json
       node scripts/governance.mjs upgrade propose knos_meter   <knos_meter buffer> --ungated --out meter.json
       node scripts/governance.mjs upgrade propose knos_passkey <knos_passkey buffer> --ungated --out passkey.json

   Each prints the proposal index, the executable hash it carries and the time from which it can execute (approval
   + 691,200 s). Compare the printed hash with the table above.

3. **Wait 8 days.** In that time anyone can read the proposals on chain; `node scripts/governance.mjs cancel upgrade
   <index>` (two members) withdraws one.

4. **Execute**, any member, after the time lock, each with the hash it must carry:

       node scripts/governance.mjs upgrade execute <index> --expect-hash <executable hash from the table>

   Order: any. No account changes its layout, and the running power of a half-verified token is the same bytes in
   both builds, so a Step sent before the upgrade finishes after it.

5. **After execution.** `solana-verify get-program-hash -u devnet <program id>` must print the table's hash. Then set
   `KNOS_OIDC_VERIFY=auto` (or make it the default in `knos.platform.verify`) so relays send one Step instead of two,
   and update programs-v2/README.md's table, web/upgrades.json and docs/reference/PROVENANCE.md.

## Timing

If the proposals are approved on day D, they can execute from D + 8 days. If SIMD-0500 activates on devnet before
D + 8, these v3 buffers are still accepted (only v0, v1 and v2 deployments are refused). If it activates before any
proposal is made, nothing changes for these v3 buffers either. What must not happen is proposing a v0 or v2 build (the v2 knos_oidc alternative included) within
8 days of activation.
