# Knos demand check (apps/wanted/)

Part of Knos, in the Knos monorepo at `apps/wanted/`. Before anyone builds, Knos checks demand: a maker describes an
idea, Qloo's taste data answers who wants it, where, against which rivals and whether interest is rising, the maker
confirms every match Qloo proposes, and the demand report goes into the Knos Record. Buyers then lock pre-orders for
that exact report in a Knos escrow on Solana devnet, and a buyer agent ranks the products that are not built yet
against tastes the buyer chooses.

**Directional demand evidence, not a sales forecast.** Every Qloo result describes
aggregate taste, not a prediction about one person. The report does not predict units, revenue or price.

Full reference: [docs/reference/DEMAND_CHECK.md](../../docs/reference/DEMAND_CHECK.md).

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

Without a Qloo credential on the server the demand check runs on Knos's **MOCK (synthetic, not real Qloo data)** MCP
server, which lists the same ten tools and answers in the same envelope. The mode and the reason are on the page
header, on every report, on every row of the trail and in every API answer.

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
| `QLOO_API_KEY` (+ `QLOO_BASE_URL`, `QLOO_TRUSTED_BASE_URL` = `https://hackathon.api.qloo.com`) | live Qloo data | MOCK (synthetic) data, labelled |
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
