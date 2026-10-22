# Pay on proof from any source

Until 0.3.34 every Knos work order was released by a forge: a workflow at a pinned commit, run on GitHub or
gitlab.com, whose token `knos_oidc` verified on chain. Research does not all live on a forge.

This page is what knos_pay 0.3.34 adds so that the machine judge pays on proof from any source, and what it
does not do yet.

**Status.** Built and tested in LiteSVM (test builds). The referee-panel path ran on devnet at a test program id this
build's agent owns (section 8). The real knos_pay program (`5y7iWJ1V…`) is NOT changed: its upgrade buffer (written, held by the vault) waits for
the founder's Squads vote (section 9). No real Google Confidential Space token and no real ORCID id_token has been
verified: those paths are tested with test issuer keys registered for the issuers' real URLs. Synthetic data only.

## 1. One door, one reader per issuer family

Every instruction that takes a token goes through `issuers::checked` (programs-v2/knos_pay/src/issuers.rs): the
account is knos-oidc's and VERIFIED, its issuer family is one the instruction accepts, it is fresh, and the key that
verified it is still usable. Then the family's own reader reads the claims.

| family | told by | reader | what it may do |
|---|---|---|---|
| GitHub Actions | knos-oidc issuer number 0 | gh.rs | everything it did before (unchanged) |
| gitlab.com CI | issuer number 1 | gl.rs | fund and pay a work order (unchanged) |
| private key | issuer number 3 + registrant | gh.rs | pay a private order of the registrant's Balance (unchanged) |
| Google Confidential Space | issuer 2, sha256 of `https://confidentialcomputing.googleapis.com` | cs.rs | pay an order that pins a container image |
| ORCID | issuer 2, sha256 of `https://orcid.org` | orcid.rs | bind an ORCID iD to a wallet (Bind) |

A private key registered under Google's or ORCID's URL stays PRIVATE: the number is read first.

**No new instruction number.** The new paths ride on instructions that exist: FundOrderWallet (15) with options byte
35, PayOrder (17) with a Confidential Space token or with a verdict as data, RefundOrder (22) with a FAIL verdict as
data, and Bind (8) with an ORCID id_token. One account kind is new: a verdict's tally (80 bytes).

**Compatibility.** GitHub and GitLab tokens pass the same checks in the same order with the same error codes; orders of
earlier builds have zero in the new judge byte and take the old path. Checked three ways: the Rust replay vectors of
2.2's scenarios (`programs-v2/testdata/*.json`, answers and account bytes) regenerate byte-identical against the
0.3.34 test build; the existing order, job, quorum, relay, GitLab, Bind and IDL tests pass against it; and the unit
tests of the program pass unchanged.

## 2. A container image as the judge (Google Confidential Space)

**This path is not used by Knos and has never run.** It needs a Google Cloud billing account, and Knos has none. The
code referee Knos uses runs in GitHub Actions instead. Its run's OIDC token is verified on chain by knos_oidc, and its
verdict carries a Sigstore attestation (REFEREE_FROST.md, "The code referee's attestation"). What follows describes
the program's code only.

An order funded with judge 1 pins a container image digest. PayOrder pays it on a Confidential Space attestation
token when:

- `iss` is `https://confidentialcomputing.googleapis.com` and its key is registered in knos-oidc (RS256; the two
  keys of its JWKS were RSA-2048 on 14 Oct 2026, so knos_oidc verifies them as deployed);
- `swname` is `CONFIDENTIAL_SPACE`, `dbgstat` is `disabled-since-boot`, `secboot` is true, `hwmodel` is
  `GCP_AMD_SEV`, `GCP_AMD_SEV_ES` or `GCP_INTEL_TDX`;
- `submods.container.image_digest` is the pinned `sha256:` digest, and
  `submods.confidential_space.support_attributes` holds `STABLE` or `USABLE`;
- `aud` is `knos3:proof:<order>:<evidence sha256 hex>:<terms hash hex>:<payees>` (Google allows 512 bytes);
- `exp` is at most an hour after `iat`.

Claim names and values: [token claims](https://docs.cloud.google.com/confidential-computing/confidential-space/docs/reference/token-claims);
algorithm: [validation fields](https://docs.cloud.google.com/confidential-computing/confidential-space/docs/reference/token-validation-endpoint-fields)
("Confidential Space supports the RS256 algorithm"); custom audience at most 512 bytes:
[connect external resources](https://docs.cloud.google.com/confidential-computing/confidential-space/docs/connect-external-resources).
All read 14 Oct 2026. Google's pages give no token lifetime; the hour is Knos's bound.

The image is the judge: whoever runs it in Confidential Space (the funder, the researcher, a lab, Knos) gets a token
only that image's code could have asked for. The judge is pinned by its bytes, not by a forge account.

## 3. Referees for evidence no issuer signs (m of n)

An order funded with judge 2 pins a panel: `sha256("knos3:panel" || m || n || n Ed25519 keys)`, 1 <= m <= n <= 10.
Each referee signs the 32-byte verdict digest

    sha256("knos3:verdict" || program id || order || order stamp i64 LE || terms hash || evidence sha256 || verdict)

where `verdict` is the payees text for a PASS and `FAIL` for a FAIL. PayOrder with data (a PASS) and RefundOrder with
data (a FAIL) read Solana's Ed25519 precompile in the same transaction by instruction introspection: only entries whose
key, signature and message are in the precompile's own data count.

Distinct panel keys are counted; below m the signers are recorded in a tally `["vd", order, digest]`; the transaction
that brings the m-th pays the payees (PASS) or returns everything to the funder (FAIL). After the deadline RefundOrder
needs no signature.

The stamp changes with every funding of an address, so a verdict acts only on the order and the funding it was signed
for.

| attempt | answer |
|---|---|
| one referee signing twice in one transaction | counted once (below m: recorded, nothing paid) |
| the same referee again later | E_REPLAY (91) |
| a verdict signed for another order | E_CLAIMS (85) |
| old signatures after the order was refunded and funded again at the same address | E_CLAIMS (85) |
| a key outside the panel, or another m | E_CLAIMS (85) |
| one referee's PASS and another's FAIL | two verdicts, one signer each: nothing moves |
| after the deadline | E_STATE (83); RefundOrder with no data refunds |

One signature per transaction fits the 1,232 bytes of a v0 transaction with a 3-key panel and one payee; two in one
transaction were 1,298 bytes in the test (a v1 transaction, 4,096 bytes, takes them).

The off-chain mirror is `knos.platform.verdict`: `message(job, evidence_hash, verdict, amount, recipient, expiry,
nonce)`, `parse`, `outcome` ("release" for PASS, "refund" for FAIL) and `check(message, sigs, keys, m, now=, used=)`. On
chain the job is the order's address, the nonce its funding stamp, the expiry its deadline.

`check` spends the verdict it accepts: (job, nonce) goes into the caller's `used` set (or a process-wide store when none
is given), so checking the same verdict again is refused as a replay, as knos_pay refuses it on chain (E_REPLAY).

## 3a. Trust model: who decides the money

Said plainly: **whoever holds the panel keys decides the money.** On chain a referee-panel order pays, or refunds,
whatever m of its pinned keys sign. The chain does not read the oracle (a referee signs whatever its own reading says)
and does not know who holds the keys.

If the funder holds the keys, the funder can refund a stage that was met; if the keys collude with a payee, they can
name that payee. In 0.3.34 the payees are named by the verdict, not fixed at funding (see "Founder decision" below).

What Knos's client tools do about it:

- **A published referee registry**, `config/referees.yaml`: the public keys Knos accepts as referees, each labelled.
  Today it holds three DEVNET TEST keys (made by the build agent, test money only). Knos has published no production
  referee key yet; adding one, and naming who holds it, is a founder decision.
- **The panel rule** (`knos.platform.referees.panel_rule`), applied by `knos.platform.verdict.check`, the idea panel
  tools (`knos.ideas.wanted.fund_panel_ix`, `stage_verdict_ixs`, `python -m knos.ideas.devnet_panel`) and the MCP tool
  `knos_graduate`:
  - a panel holding the funder's or a payee's own key is refused (that party would judge itself);
  - a panel with keys outside the registry is refused by the command-line and MCP tools;
  - `--unlisted-panel` (`unlisted_panel=True` in Python, `"unlisted_panel": true` in a graduation verdict) uses such a
    panel anyway, and every output then says `UNLISTED PANEL`. Python callers written before the registry, which pass
    no choice, get the label and a warning.
- **`knos_graduate` (MCP) needs a signed verdict**: m signatures of a registry panel over
  `knos.graduation.graduation_message(claim_id, spec_hash, expiry)`. An unsigned `{"passed": true}` is refused.
- **Spent verdicts persist**: `knos.platform.verdict.check` keeps every verdict it accepts in
  `KNOS_HOME/verdicts/spent` (one file per verdict, created atomically), so a second check is refused in any process on
  the machine. A caller that passes its own `used` set keeps its own.

What none of this does: it does not stop a funder who writes his own client and pins his own keys. Against that, only
what is on chain helps: pinned payees at funding (below), and in time a panel the program itself checks against an
on-chain registry.

## Founder decision: pin payees at funding (next upgrade, not now)

Fixing the payees when an order is funded, so that a verdict can only release to them, needs a change to knos_pay's
program: the order would store them, and PayOrder would refuse a verdict naming anyone else. 0.3.34 changes no
program beyond the buffer already written, so this goes into the NEXT knos_pay upgrade and is not done now.

Until then, the payee is whoever the m referees name.

## 4. ORCID iDs as payees

Bind (8) takes an ORCID id_token (issuer `https://orcid.org`, RS256, one RSA-2048 key; discovery fetched 14 Oct 2026) whose
`aud` is Knos's own ORCID client id, whose `nonce` is `knos3:bind:<wallet>`, and whose `sub` is a well-formed iD with a good
check character (ISO 7064 MOD 11-2).

It writes `["bind", OR_BASE + the first fifteen digits]` (OR_BASE = 10^18: above every GitHub and GitLab id). Proofs and
verdicts then name a payee by iD: `0000-0002-1825-0097.10000.-`.

The token lives 24 hours in ORCID's own example ([ORCID's OpenID Connect
guide](https://github.com/ORCID/ORCID-Source/blob/main/orcid-web/ORCID_AUTH_WITH_OPENID_CONNECT.md)), so its marker is kept
until it cannot be fresh; a Bind is replaced only by a later sign-in. **Founder step:** register Knos's ORCID public API
client and pin its id in `orcid.rs` `ORCID_CLIENTS`; a real build binds nothing until then.

## 5. What a judged order cannot have

No forge judge (its workflows repository is zero bytes), quorum, neutral run, standing rate, AUTO, holdback, kill
fee, reservation, arbiter, judge repository or privacy salt: each needs a forge token. The presentation grace is
allowed. A Balance funds none. Money moves as for any wallet's order: in by the funder's transfer, out to payees, tip
and fee, back by RefundOrder.

## 6. Compute units (LiteSVM, test build, knos_pay's own instructions)

The referee path's numbers on devnet are in section 8 (fund about 45,000; one signature recorded about 35,000; the
m-th pays about 81,000 with one payee). In LiteSVM, with the test build and test issuer keys:

| path | CU |
|---|---|
| PayOrder on a Confidential Space token (one payee, its token account created) | 176,482 |
| Bind with an ORCID token | 56,508 |

Verifying the RS256 token itself is knos_oidc's cost (PLATFORM.md).

## 7. Keys and accounts this needs

- Google Confidential Space's and ORCID's keys in knos-oidc: RegisterIssuerKey by the pinned rotate workflow, the
  guardian's approval, Refresh every 30 days (actions on the real program by the attester and the guardian).
- Knos's ORCID client id (the founder registers it).
- A Google Cloud project to run a judge image in Confidential Space (none was used here).

Tests: `tests/test_proof_issuers.py`, `tests/test_platform_verdict.py`, `programs-v2/handlers/tests/knos_pay_proof.rs`
(replays `programs-v2/testdata/pay_on_proof.json`), unit tests in `programs-v2/knos_pay/src/{issuers,cs,orcid,order_proof}.rs`.
Clients: `src/knos/proof/issuers.py`, `src/knos/platform/verdict.py`.

## 8. Devnet

The sBPF v3 deploy build (executable hash `9ae13fb9ae35262a959a903fae7b742e07a425ab97fc05fcf38b7db1bd1f0c62`, 413,400 bytes) runs at a TEST
program id the build agent owns (the chain records when), `FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4` (deploy
`3vuk1dtYquZf4jinzXcu7h36MAQs2n4X8k5NKec9U1q14oqSwXUJUFcjCrSNLoG8LXbKgRk3C3F9qayLiiMCSM6w`; bytes read back equal to the build).

Labelled internal dogfooding: a test mint of the agent's own (6 decimals, no value), synthetic evidence, three fresh referee keys, payee named by
ORCID's example iD with an address.

| step | signature | bytes | knos_pay CU |
|---|---|---|---|
| fund an order judged by a 2-of-3 panel | `2Fw9aQZS59v4eaYo41suAHavYLwSQrhSVjrfPBajHGLZtBHkA3qnpHn6krQpcbBu8dhTVXnx955gyKKjx5cArnr9` | 681 | 45,167 |
| PASS, referee 1 of 2: recorded | `2AZVrYsELBNSACYCFnG3XeydRDK5VTrvBG9H7LRAjwgQpVobhYtx9haxvEXrYZyMY7AsBPEy5j2LycFxM9EAgHXn` | 1,157 | 34,657 |
| PASS, referee 2 of 2: 5.00 test units paid | `MDntcyKymFgrcUeZTkWg2JKtwxCzXGPvd8Ph3HXLjhQTKwEMh7z3TPoq7cS8LKEZ4d2WARFKXRdHtQxwqnbG2di` | 1,157 | 81,043 |
| fund a second order (the fail case) | `2oAntj2KHZZgPtwAMuQcP9LbNxxkPAprcZRLMU7xfeq5zRkq4Jonu2SUHdcR2rRwWZrQqkHBm8s9caFRKQXvPPxw` | 681 | 45,178 |
| FAIL, referee 1 of 2: recorded | `3uzX5db7g85AD762qnkjtcb3hx1UrUrpijQxHDfi7AT5Gy63HG2TzEhm3sDpMYGz5vagYhTRbdg8zmoNzdHFp2UL` | 822 | 25,911 |
| FAIL, referee 2 of 2: refunded to the funder | `WEF3zVbup4znZGL9MHwaFszTKJTi2rPqLoWp3XYvRTJRVuhrLpAj6LpskqmGKCJjCS9bZkRaRBMscs8VPoVVxgM` | 822 | 33,095 |

The CU column is what the knos_pay instruction itself used (the Ed25519 precompile is not a program call). The
Confidential Space and ORCID paths were not run on devnet: no Google or ORCID key is registered in the devnet
knos-oidc, and registering one is the attester's and the guardian's act on the real verifier.

## 9. The founder's Squads steps for the real knos_pay

Nothing was proposed and nothing was signed. The upgrade buffer `Dfo5pYRLY8z9yvuXDQjJQtaoqJeL7Atso8zhWy9Ehkfj` is written (with the build team's own devnet test SOL)
and its authority is handed to the upgrade vault `CKCrTBN542pVhizxuSPVg8tvdnPooNxt9B7o97VuTjz2` (multisig
`9HcsMEo2o6zZu9t1kbFWpnyKn7hiHaZYYFwNHZSpmWqK`). The exact steps, with the buffer address and the executable hash,
are in `deploy/upgrade-0334/STEPS.md`.
