# Demand check: is it wanted, before anyone builds it

**In plain words.** Knos pays for work that is proven done. Before the work, a maker wants to know whether anyone
wants the thing at all. Knos's demand check asks Qloo's taste data (who, where, rising or not, against which
rivals), makes the maker confirm every match Qloo proposes, writes the demand report into the Knos Record, and lets
buyers lock pre-orders for that exact report in a Knos escrow on Solana devnet. A buyer agent ranks the products that
are not built yet against tastes the buyer chooses. The code is [`apps/wanted/`](../../apps/wanted).

Every Qloo result is aggregate taste, not a prediction about one person. A report is directional demand evidence,
not a sales forecast.

## How Knos reaches Qloo

```
browser --> Knos server (Python) --JSON lines--> apps/wanted/bridge/qloo_bridge.mjs --MCP stdio--> qloo mcp --> Qloo
                                                  (official MCP SDK 1.30.1)          (@qloo/qloo-harness 0.1.26+)
```

- Only Qloo's supported stack: `qloo mcp`, the canonical local MCP server of the public harness, started from the
  backend with the official MCP SDK, as Qloo's starter `starter/mcp-client/backend.mjs` does
  ([qloo-hackathon-kit](https://github.com/qloo/qloo-hackathon-kit)). Not used: hosted MCP endpoints (there are
  none), the legacy `qloo api mcp`, the integrate/plan/build modes. `qloo api` is not needed: the nine workflows
  cover every question below.
- Why a Node sidecar and not a Python MCP client: it is the SDK and version Qloo's starter pins, the harness
  already needs Node 22.19+, and the Python service stays on the standard library.
- Mode: **live** when `qloo_capabilities` reports `adapter.ready: true` (a credential is configured on the server);
  otherwise **MOCK**: Knos's own MCP server (`knos_wanted.mock_mcp`) with the same ten tool names and the same
  envelope, every answer labelled "MOCK (synthetic, not real Qloo data)". `python -m knos_wanted status` says
  which, and why, without calling Qloo.

## The maker flow

| # | Step | Tool | Request (smallest that answers) |
|---|---|---|---|
| 1 | the idea's taste words become tag URNs | `qloo_find_tags` | `{query, limit: 5}` per word, at most 3 words |
| 2 | existing products that stand for the idea, and its rivals | `qloo_describe` | `{entity, type}`; an ambiguous name returns candidates |
| 3 | **the maker confirms** which tag and which entity each word means | (none) | only offered candidates are accepted; "none of these" and "look up another name" are offered |
| 4 | who | `qloo_audience_demographics`, `qloo_entity_tags` | the confirmed proxy's id; up to 3 proxies for tags |
| 5 | where | `qloo_where_popular` | `{entity: id, within: place, limit: 10}` |
| 6 | rising or not | `qloo_trends` | proxy + rivals (at most 5), the last 12 weeks |
| 7 | vs rivals | `qloo_compare_audiences` | proxies (A) against rivals (B) |
| 8 | fit | `qloo_rank` | variants and rivals as options, the place as `signal_location`, an audience phrase when the idea names one |
| 9 | the report | (Knos) | sections, the lean (Knos's rule, in the app README), the trail, the report's sha256 |

The idea's text never leaves the Knos server: only the planner's search words do.

## The buyer agent flow

1. The buyer names things they like (brands, places, films) and a vibe or two, never who they are.
   `knos_wanted.privacy` refuses e-mails, phone numbers, handles, links, addresses and sentences about a person
   before any call.
2. `qloo_describe` per liked thing and `qloo_find_tags` per vibe; the buyer confirms each match.
3. `qloo_recommend` per target type the buyer picks: what people with this combined taste also like.
4. `qloo_rank` on the products open for pre-order: a product that is not built has no Qloo entity, so Knos ranks the
   existing product its maker confirmed as its proxy, one call per product type (Qloo ranks one option type per call
   and says scores from separate calls are not comparable).
5. Pre-order: the existing Knos graduation pre-order (`knos.graduation.preorder_ix`, a knos_pay FundOrderWallet),
   by the demo buyer (the app's devnet test wallet) or the buyer's own wallet.

Knos keeps no copy of a buyer's tastes: the session lives in the server's memory for 30 minutes and is not recorded.

## The request-to-result trail

Every call adds one row: the step, the tool, the request as sent (no key, no personal data), why it was asked, the
status (`ok`, `empty`, `needs_input`, `partial`, `degraded`, `error`), the result count, retries and whether it came
from the cache. Every confirmation adds a row naming the chosen id. The page shows the trail under the heading
"aggregate taste, not a prediction about one person"; its sha256 goes into the Knos Record.

## Record, anchor, fees

| Event | Knos Record (Sibyl) | Fee line (config/fees.yaml) |
|---|---|---|
| demand report | WARM claim `demand:<hash>` + COLD `experiment` | none: the report is free until the founder sets a price |
| pre-order locked | COLD `funding` + the claim's new state | `funding` (0 at lock) |
| pool paid to the maker on delivery | (the payout path of Knos) | `payout` (taken by knos_pay at release), `graduation` (decided, collected off chain) |
| anchor | Merkle root of the unanchored lines in one devnet Memo transaction, after each pre-order | none |

Public lines hold hashes, statuses, tool names, addresses and amounts: never the idea text, a buyer's tastes or a
Qloo result.

## Rules kept

- Key only on the server (`QLOO_API_KEY` in the server's environment, or `qloo setup --qloo`): never in the
  browser, the repository, a log or a recording. The bridge forwards the environment to `qloo mcp` and reads no value.
- Bounded retries: only when the envelope says `error.retryable`, at most two more, with backoff.
- Minimal cache: live `ok`/`empty` answers only, 15 minutes, at most 200 files, under `.cache/` (git-ignored).
  MOCK answers are never cached. No Qloo response is committed; the tests use synthetic bodies only.

## What a report does not establish

- It describes how audiences of EXISTING products behave, not whether this product will sell: no units, revenue,
  price or conversion.
- It depends on the matches the maker confirmed; another proxy gives another report (that is why the maker
  confirms, and why the choices are in the trail and the hash).
- Ranks and affinities are relative within one call; scores from separate calls are not comparable.
- In MOCK mode every number is synthetic and says so.
- A pre-order on devnet is test money: it shows the flow, not willingness to pay.

## Run it

```bash
npm install --global @qloo/qloo-harness && qloo --version           # 0.1.26 or newer
sh apps/wanted/bridge/install.sh                                      # the official MCP SDK beside the bridge
PYTHONPATH=src:apps/wanted python -m knos_wanted status
PYTHONPATH=src:apps/wanted python -m knos_wanted serve
PYTHONPATH=src:apps/wanted python -m pytest -q apps/wanted/tests     # no network, no key
```

With a key: `qloo setup --qloo` (typed once into the hidden prompt), then `qloo setup --status` must say "Qloo data:
ready" before a live demo.
