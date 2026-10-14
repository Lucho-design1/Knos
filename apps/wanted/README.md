# Knos Wanted

This app lives in the Knos monorepo at `apps/wanted/` (it was the separate repository drexthealpha/knos-wanted until
Knos 0.3.31; that repository is no longer where it is kept). Every command below runs from this folder.

Describe a product idea in plain English. Knos Wanted asks Qloo's taste data who would want it, where, how it stands
against its rivals and whether interest is rising, and explains why. Then it lets buyers lock pre-orders for that
exact report in a Knos escrow on Solana devnet.

**Directional demand evidence, not a sales forecast.** The report shows how an audience's tastes line up with the
idea's closest existing proxies. It does not predict units, revenue or price.

## Try it

```bash
python -m knos_wanted serve            # http://127.0.0.1:8080, no login, no key needed
python -m knos_wanted report "A late-night oat-milk coffee bar for students in London"
```

With no `QLOO_API_KEY` the app runs on **MOCK (synthetic, not real Qloo data)** responses shaped from Qloo's public
docs. The mode is shown on the page header, on every report and in every API answer.

## What is Qloo-powered

Every number in a Wanted Report comes from one Qloo call (or, in MOCK mode, from a synthetic body in the same shape).
Each report section names its call. The agent around the calls is ours: the planner, the lean rule, the page and
the escrow.

| Report part | Qloo call | What Qloo provides |
|---|---|---|
| Proxies and rivals | `GET /search` | the Qloo entity ids for the existing brands, places or works that stand for the idea and for its rivals |
| Taste tags | `GET /v2/tags` | the Qloo tag ids for the idea's keywords |
| **Who** | `GET /v2/insights?filter.type=urn:demographics` | age and gender affinity of the idea's proxies and tags (above 0 = leans in more than average) |
| **Where** | `GET /v2/insights?filter.type=urn:heatmap&filter.location.query=...` | affinity and popularity per geohash cell around the named place |
| **How strong vs rivals** | `GET /v2/insights` with the idea's tags and audience as signals and `filter.results.entities` = proxies and rivals | each entity's affinity for the same audience |
| **Rising or not** | `GET /v2/trending` | population percentile over the last 12 weeks for the main proxy |
| **Why** | `GET /v2/insights` with `feature.explainability=true` | what else this audience likes, and which of the idea's inputs drove each result |
| **Compare** | `GET /v2/analysis/compare` (A = proxies, B = rivals) | the entities Qloo returns for that comparison |

Not Qloo-powered: turning the idea into search words (keyword rules by default, or any OpenAI-compatible LLM you
configure; it proposes words only, never numbers), the one-word lean, the page, and the pre-order escrow (Knos).

Every endpoint, parameter and field above is checked against Qloo's docs, with page dates, in
[docs/QLOO_SOURCES.md](docs/QLOO_SOURCES.md).

## How the lean is decided (our rule, not Qloo's)

- **Strength:** +1 if the idea's best proxy scores at or above its strongest rival for the audience, else -1.
- **Trend:** +1 if the population percentile rose by 2 points or more over 12 weeks, -1 if it fell by 2 or more.
- **Audience:** +1 if one age segment leans in with a demographic affinity above 0.1.

Two or more points: "leans wanted". 0 or 1: "mixed". Below 0: "weak". Fewer than two of these sections with data:
"insufficient evidence". The thresholds are choices of this app, stated here so anyone can disagree with them.

## Lock pre-orders (Knos, Solana devnet, test money)

Each report gets its own pre-order pool, built with Knos's graduation code (`knos.graduation`, Knos 0.3.29): the
scope, private options and terms come from `knos.graduation.scope / options / terms`, every order is built by
`knos.graduation.preorder_ix` (a `knos_pay` FundOrderWallet), and the pool is read back with `knos.graduation.pool`.
The terms carry the report's sha256, so the money is locked against that exact report.

- The buyer's test units plus the knos_pay fee move into the knos_pay program. They are paid to the maker only on
  delivery, through Knos's judge workflow, and go back to the buyer after the deadline (14 days) otherwise. This
  app never pays anyone out.
- **Demo buyer (no wallet):** the app's own devnet TEST wallet signs, so anyone can see a real devnet escrow.
- **Your wallet:** Phantom on devnet signs in the browser; the app sends a few test units and a little devnet SOL
  first, builds the unsigned transaction, and relays only a single knos_pay pre-order signed by that wallet.
- Devnet only (`knos.chain` refuses mainnet), test units of a mint this app creates, no real money.

First devnet run (14 Oct 2026, on a MOCK report, so the report itself is synthetic; the transactions are real devnet
transactions on the public knos_pay program `5y7iWJ1VAMJjnnWbbdo2a2PsWJEwTExSNpzrvQSEnS8k`):

- demo buyer pre-order, 5 test units: [`9J3xrEAF...`](https://explorer.solana.com/tx/9J3xrEAFB68UtYsYqk8oHpvK1BZZ8Tcnf9BHWiRSvvMjGd2px1woQs1PcSCJgTKJNC8to2k42YC1XsrBuzcgJy9?cluster=devnet)
- a second wallet signing its own pre-order, 6 test units: [`3BHzsWyg...`](https://explorer.solana.com/tx/3BHzsWygneRcbQQ6Ho6wKjLtk6uwj5uCcuvvycKr1s1mhUBq7nMCMZvPzaG4ZhjvZKyMe8UjHXxjThy829Snu75?cluster=devnet)
- the pool read back from devnet: 2 buyers, 11 test units locked.

## Which Qloo endpoints does my key serve?

```bash
QLOO_API_KEY=... python -m knos_wanted probe
```

calls each endpoint once with documented parameters and writes only HTTP status codes to `.cache/probe.json`
(git-ignored). The app then skips what the key does not serve and marks that section "not served"; the rest of the
report still stands.

## Qloo data rule

Qloo allows private server-side caching and forbids storing its response data in a public repository. Live
responses are cached under `KNOS_WANTED_CACHE` (default `.cache/qloo`, git-ignored) and never committed. The tests
use synthetic bodies only.

## Deploy (one service)

```bash
# from the root of the Knos checkout: the image installs Knos and this app from the same tree
docker build -f apps/wanted/Dockerfile -t knos-wanted .
docker run -p 8080:8080 --env-file apps/wanted/.env knos-wanted
```

or without Docker, from the root of the Knos checkout: `pip install . "./apps/wanted[escrow]" && HOST=0.0.0.0 python -m knos_wanted serve`. The page and the API are
the same process. `/healthz` answers `{"ok": true}`.

| Variable | Needed for | Without it |
|---|---|---|
| `QLOO_API_KEY` | live Qloo data | MOCK (synthetic) data, labelled |
| `KNOS_WANTED_DEVNET_KEYPAIR` | lock pre-orders (a devnet test wallet with a little devnet SOL; path or JSON byte array) | escrow buttons explain what is missing |
| `KNOS_WANTED_MINT` | keeping the same test mint across restarts | a test mint is created on first use |
| `KNOS_WANTED_LLM_BASE_URL`, `_API_KEY`, `_MODEL` | LLM planner (OpenAI-compatible) | keyword planner |
| `KNOS_RPC` | a devnet RPC of your choice | `https://api.devnet.solana.com` |

The rest are in [.env.example](.env.example). Per-address rate limits keep a public demo from draining the test wallet.

## Tests

```bash
# from the root of the Knos checkout, against the Knos of the same commit
PYTHONPATH=src:apps/wanted python -m pytest -q apps/wanted/tests
```

Knos's own suite runs these too (`tests/test_fold_wanted.py`). Without `knos` and `solders` importable the escrow
tests are skipped and the rest run on the standard library.

## License

MIT, see [LICENSE](LICENSE). Knos is MIT licensed. Qloo data is Qloo's and is used under its API terms.
