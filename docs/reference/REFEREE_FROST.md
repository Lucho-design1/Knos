# The referee panel as one FROST threshold key

A milestone's escrow on knos_pay is released by a referee PANEL: the order pins m of n Ed25519 keys and the program
counts their signatures through Solana's Ed25519 precompile (PAY_ON_PROOF.md). Until now Knos's devnet panel was three
keys on one server.

It is now ONE key that no machine holds: the Zcash Foundation's FROST
([frost-ed25519](https://crates.io/crates/frost-ed25519) 3.0.0, RFC 9591 FROST(Ed25519, SHA-512)) splits it into three
key shares on three hosts, and any two of them produce one standard Ed25519 signature under the group key.

| host | holds | where |
|---|---|---|
| 1 render | one share | the Knos app server (knos.onrender.com), a Render secret file (`KNOS_REFEREE_FROST_SHARE`) |
| 2 gh | one share | GitHub Actions in drexthealpha/Knos, repository secret `KNOS_REFEREE_FROST_SHARE`, `.github/workflows/referee.yml` |
| 3 pc | one share | the founder's PC, a WSL daemon (`python -m knos.threshold serve`) |

Hosts 1 and 2 complete a release when the PC is offline.

## What the deployed program accepts

`order_proof.rs` `panel_of` accepts any panel with `1 <= m <= n <= 10` distinct non-zero keys, and the tally pays at
`m` distinct panel keys that signed the verdict digest in the transaction.

A **1-of-1 panel whose one key is the FROST group key** is therefore a valid PANEL order on the knos_pay 0.3.34 test
program `FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4`, with no program change: one precompile entry (group key,
aggregated signature) releases it in one transaction. Tested in LiteSVM against
`tests/fixtures/knos_pay_v2_0334_test.so` (`tests/test_threshold_frost.py`).

The group key (devnet test): `CZ599fmDD6ATkRsbUbdZiAQE7uF9sJrGFmJ6k54ujb4E`, panel `1:CZ599fmD…`, public record
`config/referee-frost.json`, also in `config/referees.yaml`.

## How a release is signed

1. The maker posts evidence (`POST /api/milestone`). The app server checks it, opens a signing session for the stage's
   verdict digest and signs as host 1. Hosts 2 and 3 poll `/api/referee/pending`: `referee.yml` runs on a cron every
   5 minutes (and on workflow_dispatch), the PC daemon every 30 s. No founder-made token starts host 2.
2. Each host **re-checks the milestone itself** (`knos.threshold.check`): it reads the order on devnet, fetches the
   evidence page (https, public address, no redirects), requires the claim id in it and recomputes the digest. A host
   never signs a digest the coordinator hands it.
3. FROST round 1: each host posts its commitments (`/api/referee/commit`). At two, the coordinator fixes the signing
   package. Round 2: the two chosen hosts post signature shares (`/api/referee/share`). Every post carries the host's
   transport signature (an Ed25519 key in its share record, public key in the group record). Host 2's posts also
   carry the job's GitHub Actions OIDC token (audience `knos-referee`); the app server verifies it against GitHub's
   published keys and requires repository `drexthealpha/Knos` (by repository and owner id), workflow
   `.github/workflows/referee.yml@refs/heads/main`, ref `refs/heads/main` and a schedule or workflow_dispatch run
   (`knos.threshold.ghoidc`).
4. The coordinator aggregates (frost verifies every share), checks the signature under the group key and sends it as an
   ordinary verdict of the group key (`knos.ideas.commit.release`).

Nonces live only in the signing process's memory and are used once. One share alone produces no signature.

## Key generation

`python -m knos.threshold dkg-local --out DIR` runs FROST's distributed key generation (no dealer) as three separate
processes. They exchange round-2 packages encrypted to each other (X25519, HKDF-SHA256, ChaCha20-Poly1305) through a
relay that sees only public packages and ciphertexts.

The devnet group was made this way on the founder's PC because hosts 1 and 2 run this code only after the next push.
Until the Render and GitHub shares are uploaded and deleted from the PC, that one machine held all three shares.

## The code referee's attestation (GitHub Actions, knos_oidc on chain, Sigstore)

The referee is code: `knos.threshold.check.milestone_digest`, run by each host itself. Host 2 runs it in GitHub
Actions, and that run is attested with no account anywhere (`knos.threshold.codeattest`):

1. **The verdict.** For every session whose digest its own check recomputed, `referee.yml`'s job `sign` writes one
   verdict file (canonical JSON): the session, the digest the FROST group signs, the order, the evidence page's
   sha256, and the run's repository, `workflow_ref`, commit and run id. It is kept as the run's artifact
   `referee-verdicts`.
2. **The attestation.** Job `attest` holds no key share and no secret. It runs `actions/attest-build-provenance`
   v4.2.2 over the verdict files: a SLSA v1 provenance statement, signed keyless through Sigstore's public-good
   instance (a Fulcio certificate for the run's OIDC identity, logged in Rekor). The app server checks the bundle
   against Sigstore's public trust root with Knos's own Sigstore adapter (`knos.sources.sigstore`, whose trusted
   root is pinned by sha256). For a bundle in a Rekor log that adapter cannot read, it uses sigstore-python 4.5.0.
   The certificate identity must be
   `https://github.com/drexthealpha/Knos/.github/workflows/referee.yml@refs/heads/main`, issued by GitHub Actions, at
   the verdict's commit, and the statement's subject must be the verdict's sha256. Anyone can check the same:
   `gh attestation verify verdict-<session>.json -R drexthealpha/Knos`, or
   `python -m knos.threshold.codeattest verify verdict-<session>.json`.
3. **On chain.** The same job asks for an OIDC token with the audience `knos-referee:verdict:<sha256 of the verdict>`
   and posts it with the verdict to `POST /api/referee/attest`. The server verifies it (`knos.threshold.ghoidc`:
   referee.yml on main of drexthealpha/Knos, by repository and owner id). Then the deployed knos_oidc verifies it on
   devnet (`knos.settle.v2.relay.verify_only`: Write, then Step, RS256 under GitHub's key; the relayer pays the fee).
   The token account `["tok", relayer, sha256(token)]` is then VERIFIED, owned by knos_oidc, and holds the decoded
   claims: `repository`, `workflow_ref`, `sha`, `run_id`, and the audience that names the verdict's hash. No program
   was changed for this. It is the verify path that knos_oidc already has.
4. **The release** is unchanged: 2 of the 3 hosts sign the digest the verdict names.

The session records all of this (`code_referee`), and the project milestone page shows four links per order: the
referee run, the knos_oidc verification transaction, the Sigstore attestation (GitHub's attestation page and its Rekor
entry) and the FROST release transaction.

`knos.threshold.attest` (a Google Confidential Space token verifier) is **unused**: nothing calls its `verify`.
ghoidc uses its RS256 helpers. It is kept only because it is tested. Knos runs no Confidential Space referee and
claims none.

## Limits

- The game's demo prizes (`apps/wanted/knos_wanted/tasks.py`, funded by the round's sponsor) use the FROST group too:
  the round's verdict is published at `/api/prize/evidence?id=`, and 2 of the 3 hosts fetch and re-check that page
  before they sign. Without the FROST group configured, 2 of the server's 3 keys sign as before.
- Project milestones (`apps/wanted/knos_wanted/valley.py`) pin the FROST group too: once the result and the
  independent check are in, the review (both pages' URLs and sha256s, every funded order's claim id) is published at
  `/api/project/evidence?id=`, one session opens per funded order, and the second share releases it to the maker and
  the referrer's share. Orders made before the group was configured keep the 3 server keys until they settle.
- FAIL verdicts: refunds after the deadline need no verdict. A threshold FAIL verdict is not built.
