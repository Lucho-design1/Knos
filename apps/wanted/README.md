# Knos demand check (apps/wanted/)

Part of Knos, in the Knos monorepo at `apps/wanted/`. Before anyone builds, Knos checks demand: a maker describes an
idea, Qloo's taste data answers who wants it, where, against which rivals and whether interest is rising, the maker
confirms every match Qloo proposes, and the demand report goes into the Knos Record. Buyers then lock pre-orders for
that exact report in a Knos escrow on Solana devnet, and a buyer agent ranks the products that are not built yet
against tastes the buyer chooses.

**Directional demand evidence, not a sales forecast.** Every Qloo result describes
aggregate taste, not a prediction about one person. The report does not predict sales, revenue or price: the target
and reserve of a pre-order campaign come from a published formula over Qloo's numbers, not from a forecast.

Full reference: [docs/reference/DEMAND_CHECK.md](../../docs/reference/DEMAND_CHECK.md). License: MIT ([LICENSE](LICENSE)).

## Research stuck in the valley of death (the intake)

`POST /api/research {ref}` (the page's first box): a DOI, arXiv id, PubMed id, OpenAlex id (W...) or `uspto:<number>`
(labelled FIXTURE without a USPTO key) is read through `knos.ideas.sources` and OpenAlex into a research card
(`knos_wanted/research.py`): the proven result (an abstract sentence chosen by a fixed rule, quoted with its DOI),
OpenAlex `cited_by_count`, year, retraction status (Crossref `updated-by`, OpenAlex `is_retracted`), Nobel recognition
from `knos_wanted/data/nobel.toml` (each row quotes and links its nobelprize.org press release), and the product it
enables (the Nobel release's named use, else a topic table, else a generic phrase; the maker edits it). The demand check
then runs on that product, and the report adds "why it never crossed": money before proof, slow judges, failed
attempts, each flagged only with its evidence, else "no evidence".

Wake page: `web/wanted.html`, served by GitHub Pages at https://drexthealpha.github.io/Knos/wanted.html (scripts/build_site.sh copies web/), pings `https://knos.onrender.com/healthz` until the free instance wakes,
then opens the app; the app shows a status line during slow calls.

The Knos Record (Sibyl) is read before money moves: `/api/check` writes the decision (WARM claim `demand:<hash>`, COLD
`experiment`); a pre-order is refused unless Sibyl holds that report as OPEN with the same target and reserve; a
release needs Sibyl's pre-order entry and is refused when Sibyl already holds it as released; the reserve is counted
from Sibyl. Needs `sibyl-memory-client>=0.8.1,<0.9` (pinned by Knos's pyproject, installed in the image).

## The check, the decision, the money (Qloo REST, the primary path)

1. **Check** (`POST /api/check {idea, place?, leader?}`, no sign-in): the idea's key words go to Qloo's API from this
   server (`knos_wanted/qloo_rest.py`): `/search` + `/entities` (closest products, the market leader), `/v2/tags`
   (the idea's taste tags), `/v2/insights` with `urn:demographics` (who), `urn:heatmap` (where), `urn:audience`
   (segments), `/v2/trending` (rising or falling) and `/v2/analysis/compare` (overlap and whitespace vs the leader).
   Every number in the report names the call that produced it. The maker confirms the matches: the page lists them
   with a tick each; unticking wrong ones and pressing "Decide again" re-runs the check without them (`exclude`).
2. **Decision, by code** (`knos_wanted/check.py`, `RULES`): OPEN pre-orders with a target and a reserve, or REFUSE
   with reasons (no matching taste data, audience too thin, falling trend, the leader already owns the space). With
   no Qloo key or a failed essential call the answer is "cannot decide: no Qloo evidence": nothing opens without Qloo.
3. **Pre-order** (`POST /api/preorder`, signed in): test units locked on Solana devnet through `knos.ideas.commit`, one
   stage "milestone" judged by a 2-of-3 referee panel on the knos_pay 0.3.34 test program. Demo buyer, test money.
4. **Milestone** (`POST /api/milestone {commitment, evidence_url}`): code fetches the maker's https page (public
   addresses only, no redirects, 512 KB, 10 s) and requires the commitment's claim id on it; then two referees sign
   PASS over the page's sha256 and the server releases to the maker, once the report's reserve is met. Otherwise the
   money stays locked and `POST /api/refund` returns it after the deadline.
5. **Business model**: Knos takes the payout fee of `config/fees.yaml` (0.3%, at least 0.05) only on money released on
   proof; the program holds it with the money and a refund costs the buyer nothing. The page shows the line it reads.

Sign-in: a passkey (WebAuthn; the identity is derived from the passkey's public key), Google (only when
`GOOGLE_CLIENT_ID` is set; the ID token is checked with Google's tokeninfo endpoint), or an email typed as a display
label only (no email provider is configured: nothing is sent or verified, and the page says so).

Agents: `knos mcp` lists `knos_demand_check` when `KNOS_MCP_TOOLS=demand`; it POSTs to the hosted app
(`KNOS_WANTED_URL`), so an agent gets the same code-made decision without a Qloo key.

### Run it locally

```sh
# from the root of the Knos checkout
pip install . "./apps/wanted[escrow]"
export QLOO_API_KEY=...                                   # server side only; never in the page
export QLOO_BASE_URL=https://hackathon.api.qloo.com
PYTHONPATH=apps/wanted python -m knos_wanted serve        # http://127.0.0.1:8080
```

### Environment (names only)

| Variable | What |
|---|---|
| `QLOO_API_KEY`, `QLOO_BASE_URL` | Qloo's key (header only, never logged) and API base |
| `QLOO_MONTHLY_BUDGET` | hard cap on uncached Qloo calls per month (default 9000); cached answers still served |
| `KNOS_WANTED_CACHE`, `KNOS_WANTED_STATE` | private cache (7 days) and state folders on the server |
| `KNOS_WANTED_DEVNET_KEYPAIR` | the demo buyer's devnet test wallet (also the test mint's authority) |
| `KNOS_WANTED_REFEREE_KEYS` | JSON list of 3 devnet test referee secret keys (one server: not an independent panel) |
| `KNOS_WANTED_MAKER_WALLET` | default payee (the maker's devnet wallet) |
| `KNOS_WANTED_RELAYER_KEYPAIR`, `KNOS_WANTED_MINT`, `KNOS_WANTED_PROGRAM`, `KNOS_WANTED_MILESTONE_DAYS` | optional |
| `GOOGLE_CLIENT_ID`, `KNOS_WANTED_SESSION_SECRET`, `KNOS_WANTED_RP_ID` | sign-in |
| `KNOS_WANTED_URL` | for `knos mcp`: where the hosted check lives |

Without the escrow variables the pre-order endpoints answer "escrow unavailable on this server"; the report still works.

### What changed since 30 Sep

- Qloo's REST API is the primary path (cache, 4 calls/s, monthly budget); the qloo-harness MCP sidecar stays optional.
- A decision made by code (OPEN with target and reserve, or REFUSE with reasons); "cannot decide" without Qloo.
- Pre-orders are paid on proof: one milestone, a 2-of-3 referee panel, release only after code verifies the evidence.
- Sign-in (passkey, Google when configured, a label), a mobile-first page, and the `knos_demand_check` MCP tool.

## Try it

```bash
# once: Qloo's harness (Node 22.19+) and the official MCP SDK beside the bridge
npm install --global @qloo/qloo-harness          # qloo --version must be 0.1.26 or newer
sh apps/wanted/bridge/install.sh                 # @modelcontextprotocol/sdk 1.30.1, as Qloo's starter pins it

# from the root of the Knos checkout
PYTHONPATH=src:apps/wanted python -m knos_wanted status                     # live or MOCK, and why (no Qloo call)
PYTHONPATH=src:apps/wanted python -m knos_wanted serve                      # http://127.0.0.1:8080, no login
PYTHONPATH=src:apps/wanted python -m knos_wanted maker "A late-night oat-milk coffee bar for students in London" \
    --rival Starbucks --rival Pret --pick first                             # the maker flow in a terminal
```

**Without a Qloo key the build refuses to decide.** `POST /api/check` answers CANNOT_DECIDE ("cannot decide: no Qloo
evidence") with zero Qloo calls, `/api/status` says `qloo_rest.rest: false` and `no_key_behaviour`, the page badge
says "Qloo: off", and pre-orders never open. With the key set, `/api/status` reports `mode: live` (the REST path).
Only the older terminal/MCP flow below (`maker`, `buyer`) still falls back to Knos's MCP server,
**MOCK (synthetic, not real Qloo data)**,
when the harness has no credential; every answer of that flow is labelled so, and none of it can
open pre-orders.

## What is Qloo-powered

Qloo is reached only from the server, only through Qloo's canonical local MCP server `qloo mcp`
(@qloo/qloo-harness), started by `bridge/qloo_bridge.mjs` with the official MCP SDK exactly as Qloo's starter
`starter/mcp-client/backend.mjs` does. Nine workflows, each where it answers a question of the product:

| Step | Tool | Why |
|---|---|---|
| Maker: the idea's taste words | `qloo_find_tags` | turn "oat-milk", "late-night" into tag URNs the maker picks from |
| Maker: what stands for the idea, and its rivals | `qloo_describe` | resolve existing products to one Qloo entity each; ambiguous names come back as candidates the maker confirms |
| Who | `qloo_audience_demographics`, `qloo_entity_tags` | aggregate age and gender affinity of the proxy's audience; the concepts that characterise it (and whether the maker's chosen taste is among them) |
| Where | `qloo_where_popular` | heatmap cells around the maker's place |
| Rising or not | `qloo_trends` | population percentile over 12 weeks for the proxy and the rivals |
| Vs rivals | `qloo_compare_audiences` | the proxy's audience against the rivals' |
| Fit | `qloo_rank` | which variant of the idea or rival fits this place and audience best |
| Buyer: what this taste also likes | `qloo_recommend` | per target type the buyer picks, from the buyer's confirmed signals |
| Buyer: which unbuilt product fits | `qloo_rank` | the confirmed proxies of the products open for pre-order, against the buyer's signals |

`qloo api` is not used: the workflows cover every question. Not Qloo-powered: the planner that proposes search words
(keyword rules by default, or any OpenAI-compatible LLM you configure; it proposes words only, never numbers), the
one-word lean, the page, the Knos Record and the pre-order escrow (Knos).

## How the lean is decided (Knos's rule, not Qloo's)

- **Fit:** +1 if a variant of the idea ranks above every rival in `qloo_rank` for the place and audience, else -1.
- **Trend:** +1 if the proxy's population percentile rose by 2 points or more over 12 weeks, -1 if it fell by 2 or more.
- **Audience:** +1 if one age segment leans in with a demographic affinity above 0.1.

Two or more points: "leans wanted". 0 or 1: "mixed". Below 0: "weak". Fewer than two of these sections with data:
"insufficient evidence". The thresholds are choices of Knos, stated here so anyone can disagree with them.

## Record and money

- Every demand report: a WARM claim `demand:<report hash>` and a COLD `experiment` event in the Knos Record
  (`knos.record`, Sibyl). Every pre-order: a COLD `funding` event and the claim's new state. After each pre-order
  the unanchored lines are anchored on Solana devnet (`knos.record.anchor`, signed by the app's devnet test wallet);
  `python -m knos_wanted anchor` does it on demand. The record holds hashes, statuses, tool names, addresses and
  amounts: never the idea text (only its sha256), never a buyer's tastes, never a Qloo result.
- Pre-orders use Knos's graduation pre-order pool (`knos.graduation.preorder_ix`, knos_pay FundOrderWallet): money
  is paid to the maker only on delivery through Knos's judge, and refunded after the deadline (14 days) otherwise.
- Fees come from `config/fees.yaml` (`knos.money.fees_config`): `funding` 0 at lock, `payout` taken by knos_pay at
  release, `graduation` decided and collected off chain. The demand report has no fee line: it is free until the
  founder sets one. Devnet only, test units of a mint this app creates, no real money.

## Qloo data and personal data

- The key lives only in the server's environment (`QLOO_API_KEY`) or the harness's private config (`qloo setup
  --qloo`). It never reaches the browser, the repository, a log or a recording.
- No personal data goes to Qloo: `knos_wanted.privacy` refuses e-mails, phone numbers, handles, links, addresses
  and sentences about a person before any call. Buyers name things they like, never who they are.
- Smallest requests (limits of 3 to 12), bounded retries (only when Qloo says `retryable`, at most 2 more, with
  backoff), and a minimal private cache (live answers only, 15 minutes, at most 200 files under `.cache/`,
  git-ignored). No Qloo response is ever committed; the tests use synthetic bodies only.

## Deploy (one service)

```bash
# from the root of the Knos checkout: the image installs Knos, this app, Node, the harness and the MCP SDK
docker build -f apps/wanted/Dockerfile -t knos-demand .
docker run -p 8080:8080 --env-file apps/wanted/.env knos-demand
```

| Variable | Needed for | Without it |
|---|---|---|
| `QLOO_API_KEY` (+ `QLOO_BASE_URL`, `QLOO_TRUSTED_BASE_URL` = `https://hackathon.api.qloo.com`) | live Qloo data | the check answers CANNOT_DECIDE (no Qloo evidence); the MCP flow runs MOCK (synthetic), labelled |
| `KNOS_WANTED_DEVNET_KEYPAIR` | pre-orders and anchoring (a devnet test wallet with a little devnet SOL; path or JSON byte array) | escrow buttons explain what is missing |
| `KNOS_WANTED_MINT` | the same test mint across restarts | a test mint is created on first use |
| `KNOS_WANTED_RECORD` | where the Knos Record lives | `~/.knos/record` |
| `KNOS_WANTED_LLM_BASE_URL`, `_API_KEY`, `_MODEL` | LLM planner (OpenAI-compatible) | keyword planner |
| `KNOS_RPC` | a devnet RPC of your choice | `https://api.devnet.solana.com` |

## Tests

```bash
# from the root of the Knos checkout; no network, no key: Knos's MOCK server is the fake MCP server
PYTHONPATH=src:apps/wanted python -m pytest -q apps/wanted/tests
```

`tests/test_bridge.py` drives the real Node bridge and SDK against the MOCK server as a separate process; it is
skipped, with the reason, where Node or the SDK is not installed. Knos's own suite runs these too
(`tests/test_fold_wanted.py`).

## License

MIT, see [LICENSE](LICENSE). Knos is MIT licensed. Qloo data is Qloo's and is used under its API terms.
