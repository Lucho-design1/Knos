# Upgrade 0.3.34: knos_pay pays on proof from any source, through the upgrade multisig

**For the founder.** Nothing here has been proposed, approved or executed, and no founder or member key signed
anything. The V34PAY build agent built knos_pay 0.3.34 as sBPF v3, deployed that same build to a devnet test program
of its own to exercise it, and prepares one upgrade buffer for the real knos_pay with its own wallet. Only a proposal
of the upgrade multisig `9HcsMEo2o6zZu9t1kbFWpnyKn7hiHaZYYFwNHZSpmWqK` that two members approve, executed after its
691,200-second (8-day) time lock, can put the buffer's bytes into the program.

| what | value |
|---|---|
| program | knos_pay `5y7iWJ1VAMJjnnWbbdo2a2PsWJEwTExSNpzrvQSEnS8k` (devnet), upgrade authority = vault |
| upgrade vault | `CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2` |
| build | sBPF v3 (e_flags 3), cargo-build-sbf 4.4.0, platform-tools v1.57, default features (devnet), 413,400 bytes |
| executable hash | `9ae13fb9ae35262a959a903fae7b742e07a425ab97fc05fcf38b7db1bd1f0c62` (`HASHES-v3.txt` beside this file) |
| buffer | `Dfo5pYRLY8z9yvuXDQjJQtaoqJeL7Atso8zhWy9Ehkfj`: written, bytes read back = build, authority = the vault (step 0) |
| knos_oidc | unchanged: the 0.3.34 paths need no verifier change |

What changes: one front door with a reader per issuer family (GitHub, gitlab.com, private keys as before; Google
Confidential Space and ORCID new), an order that pins a container image or an m-of-n referee panel instead of a forge
workflow, the verdict's PASS (PayOrder with data) and FAIL (RefundOrder with data), and Bind of an ORCID iD. No
instruction number, account layout or existing behaviour changed (docs/reference/PAY_ON_PROOF.md). This supersedes the
0.3.29 knos_pay v3 buffer `4sqFJdjHYi44jQQwyweumbFU9vrWGfWZ2bWKQYKgaKRF` (executable hash `95fa02b2…`): propose one or
the other, not both.

## Founder decision recorded: payees pinned at funding go in the NEXT upgrade

This buffer lets m referees name the payees in their verdict. Pinning the payees when an order is funded (so a verdict
can only pay them) needs a knos_pay program change; it is not in this buffer and is planned for the next knos_pay
upgrade. Until then, Knos's client tools accept only panels from config/referees.yaml with no party's own key
(docs/reference/PAY_ON_PROOF.md, "Trust model").

## 0. The buffer (done; no founder SOL was needed)

Written with the build team's own consolidated devnet test SOL (no founder or member key): 413,400
bytes, executable hash `9ae13fb9ae35262a959a903fae7b742e07a425ab97fc05fcf38b7db1bd1f0c62`, bytes read back equal to
the build, buffer authority handed to the vault `CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2` in transaction
`4JmTnMH1tVEJx7eUBenSzMHkSmcbUEVtutrfibWtqpQPMparp4yFMYYqdRTwMFSWTnhGdF7auH4hpfCSmnDVB9DV`. Nothing was proposed.

## 1. Check the bytes yourself

    git checkout <the knos-0.3.34 commit>
    bash scripts/build_sbf.sh v3 deploy          # knos_pay's executable hash must be 9ae13fb9…
    solana program dump -u devnet Dfo5pYRLY8z9yvuXDQjJQtaoqJeL7Atso8zhWy9Ehkfj b.so
    solana-verify get-executable-hash b.so       # must print 9ae13fb9ae35262a959a903fae7b742e07a425ab97fc05fcf38b7db1bd1f0c62
    solana program show -u devnet Dfo5pYRLY8z9yvuXDQjJQtaoqJeL7Atso8zhWy9Ehkfj   # Authority: CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2

The same bytes run at the agent's devnet test program `FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4`
(`solana-verify get-program-hash -u devnet FaMHCjzy…` prints the same hash).

## 2. Propose (two member keys approve; the founder signs, never an agent)

    node scripts/governance.mjs upgrade propose knos_pay Dfo5pYRLY8z9yvuXDQjJQtaoqJeL7Atso8zhWy9Ehkfj --ungated --out pay-0334.json

Compare the executable hash it prints with the table. (`--ungated` because the release gate records v0 builds;
step 1 is the evidence, as for the 0.3.29 v3 buffers.)

## 3. Wait the time lock, then execute

The proposal waits 691,200 seconds (8 days). `node scripts/governance.mjs cancel upgrade <index>` withdraws it.
After the lock:

    node scripts/governance.mjs upgrade execute <index> --expect-hash 9ae13fb9ae35262a959a903fae7b742e07a425ab97fc05fcf38b7db1bd1f0c62

## 4. After

- `solana-verify get-program-hash -u devnet 5y7iWJ1VAMJjnnWbbdo2a2PsWJEwTExSNpzrvQSEnS8k` prints `9ae13fb9…`.
- Register Google Confidential Space's and ORCID's keys in knos-oidc (RegisterIssuerKey: the pinned rotate workflow
  with the `issuer` input https://confidentialcomputing.googleapis.com and https://orcid.org; the guardian approves
  each key; Refresh every 30 days). Until then those two paths take no token on the real programs.
- Register Knos's ORCID public API client and pin its id in programs-v2/knos_pay/src/orcid.rs `ORCID_CLIENTS` (a
  later upgrade); until then Bind takes no ORCID token.
- Update programs-v2/README.md, web/upgrades.json and docs/reference/PROVENANCE.md with the new hash.

Timing: SIMD-0500 (no new sBPF v0-v2 deploys) is expected with Agave 4.4; a v3 buffer is accepted before and after it.
