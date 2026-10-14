<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Knos on Nemotron: Token Factory, Serverless Jobs and Tavily

**In plain words.** NVIDIA's Nemotron models write code for Knos and explain why a cheat is a cheat. Knos's referee
alone decides what is kept, and a model's words cannot change that. Tavily looks for copied code and for new tricks,
and a new trick becomes a rule only if it passes the referee's own test.

Track: **Coding and Agentic Engineering**. Code: `src/knos/nebius/`. The flow, the demo and the panel:
[examples/nebius/](../../examples/nebius/README.md). Tests: `tests/test_nebius_clients.py`, `tests/test_nebius_referee.py`,
`tests/test_nebius_demo.py`, `tests/test_nebius_flow.py`.

## The one flow (v0.3.32)

`python -m knos.nebius flow --out DIR [--wallets DIR]`: a team posts a task (sealed hidden tests; with `--wallets` a
`knos_pay` escrow on devnet) -> **Nemotron 3 Super on Token Factory writes the code and its tests, the agent runs
pytest and fixes what fails** (`knos.nebius.agent`) -> the agent pays one check over x402 on devnet -> Tavily
provenance on the agent's code -> the Knos referee judges that code on the sealed tests (a scripted, labelled
synthetic cheater is refused on the same task) -> paid (LiteSVM, labelled: `knos_pay` pays only on a GitHub Actions
OIDC token) -> metered and invoiced (`knos.money.teams`). Devnet signatures, timings, prices and the model:
[TEAMS.md](TEAMS.md).

In live mode (`NEBIUS_API_KEY`, `TAVILY_API_KEY`) the agent's every turn is a Token Factory chat completion and the
provenance check is a Tavily `POST /search` per distinctive line, with `include_usage` (tested with a recording
transport: URL, bearer header, body).

## What is live and what is MOCK

| provider | switch | in this build |
|---|---|---|
| Nebius Token Factory | `NEBIUS_API_KEY` set | not set when this was built (14 Oct 2026): MOCK |
| Tavily | `TAVILY_API_KEY` set | not set: MOCK |
| Nebius Serverless Jobs | `KNOS_NEBIUS_JOBS=1` and the `nebius` CLI on PATH | neither: re-runs ran in the local sandbox |

A MOCK reply is made locally in the documented response shape and labelled **MOCK (synthetic, not a real API
response)** in its JSON (`knos_mock`), in the panel and in the demo output. MOCK search results use the reserved
`mock.invalid` domain. The referee's runs in a MOCK demo are real: it judges the proposed files and diffs.

No live call to Token Factory, Tavily or Serverless Jobs has been made from this code yet. The request shapes are
tested against the documented ones with a fake transport; the first live run is the founder's (below).

## The API facts used, with their sources

Every page below was read on 14 Oct 2026.

| fact | value used | source |
|---|---|---|
| base URL | `https://api.tokenfactory.nebius.com/v1/` | [Token Factory docs](https://docs.tokenfactory.nebius.com/) |
| chat | `POST /v1/chat/completions`, `Authorization: Bearer <NEBIUS_API_KEY>`; body `model`, `messages`, `max_tokens`, `temperature`, `response_format`; reply `choices[].message.content`, `finish_reason`, `usage.prompt_tokens/completion_tokens/total_tokens` | [create chat completion](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion.md) |
| JSON output | `response_format` `{"type": "json_object"}` (also `json_schema`; the guide and the reference wrap the schema differently, so Knos uses `json_object` and checks the result itself) | [JSON mode](https://docs.tokenfactory.nebius.com/ai-models-inference/json.md) |
| list models | `GET /v1/models` -> `data[].id` | [list models](https://docs.tokenfactory.nebius.com/api-reference/models/list-models.md) |
| Nemotron 3 Super | `nvidia/nemotron-3-super-120b-a12b`; USD 0.30 in / 0.90 out per 1M tokens; 256K context in the catalog; us-central1 | [model catalog](https://tokenfactory.nebius.com/model-catalog.md); id also in the [launch post](https://nebius.com/blog/posts/nemotron3-super-now-available) (11 Mar 2026) |
| Nemotron 3 Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` (mixed case, as the catalog writes it); USD 1.00 in / 3.00 out per 1M tokens; 1024K context; us-central1 | [model catalog](https://tokenfactory.nebius.com/model-catalog.md) |
| Serverless Jobs | `nebius ai job create --name --image --container-command --args --platform --preset --timeout`; `get-by-name`, `get`, `logs`, `delete`; CLI profile with a project id; billed only while running | [jobs quickstart](https://docs.nebius.com/serverless/quickstart/jobs), [manage jobs](https://docs.nebius.com/serverless/jobs/manage) |
| Serverless Endpoints | `nebius ai endpoint create --name --image --platform cpu-d3 --preset 4vcpu-16gb --container-port --auth token --token`; URL from `.status.public_endpoints` | [endpoints quickstart](https://docs.nebius.com/serverless/quickstart/endpoints) |
| Tavily search | `POST https://api.tavily.com/search`, `Authorization: Bearer tvly-...`; `query`, `search_depth`, `max_results`, `include_domains`, `include_usage`; reply `results[].title/url/content/score`, `response_time`, `usage.credits` | [Tavily search](https://docs.tavily.com/documentation/api-reference/endpoint/search) |
| Tavily price | basic search 1 credit, advanced 2; USD 0.008 per credit pay-as-you-go | [Tavily credits](https://docs.tavily.com/documentation/api-credits) |

The catalog lists no Content Safety model on Token Factory (searched 14 Oct 2026), so Knos uses none.

## How each part works

1. **Coder.** `coder.NemotronProposer` is a `knos.autoresearch` proposer. It sends the same prompt as the command
   proposer: program, idea, current best file, and the referee's past decisions. It never sends a hidden score.
   `coder.self_diff` asks Super for one diff for a `targets.yml` target; `coder.prescreen` runs the rules of
   `knos self check-pr` on it before anything executes.
2. **Explainer.** `explain.explain` sends the referee's verdict and findings to Ultra and copies the verdict into the
   result unchanged. A test gives it a model that says "this is fine" and the verdict stays "refused".
3. **Provenance.** `tavily.provenance` searches the three longest written lines of the best candidate. A result that
   holds one verbatim is flagged for a person to look at; the verdict does not change.
4. **New rules.** `rules_intake.draft_from_web` turns Tavily results into a rule proposal with Super.
   `rules_intake.accept` registers it with `cheats.add_rule` only if it fires on its known-bad diff, stays silent on
   its known-good diff, and the library did not already refuse the bad case. It is registered in that process only.
   Committing a rule to the library is a referee change, which needs SELF's red-team and shadow gate and the founder's
   signature ([SELF.md](SELF.md)).
5. **Re-runs.** The autoresearch referee runs every candidate twice (two seeds) in its local sandbox. With
   `KNOS_NEBIUS_JOBS=1` and the CLI, `python -m knos.nebius job TASK FILE --ref BRANCH` creates a Serverless Job.
   The job clones the repository at that branch and re-judges the file on the sealed final set. This path has not run
   against a real account.
6. **Panel.** `panel.metrics` counts tokens, latency, spend (catalog prices, Tavily credits), cost per verified
   improvement (all spend divided by the changes the referee kept) and cheats caught.

## Limits

- MOCK token counts are estimates (four characters a token) and MOCK latency is the local mock's; both are labelled.
- In the self-loop part, the demo screens the diffs (`check-pr`) but does not run `knos self run`. That run needs the
  founder's state folder, sealed bundles and jail ([SELF.md](SELF.md)).
- The autoresearch referee's static rules are a filter, not an OS sandbox ([AUTORESEARCH.md](AUTORESEARCH.md)).

## Demo URL (founder steps)

1. Get a Token Factory key and Tavily key (Nebius Builder Program), and install and configure the `nebius` CLI with
   the project id.
2. Build and push the image: `docker build -f examples/nebius/Dockerfile -t <registry>/knos-nebius:0.3.30 .`, then
   `docker push` to a registry the project can pull from.
3. `export AUTH_TOKEN=$(openssl rand -hex 32)`, then `nebius ai endpoint create --name knos-nebius --image
   <registry>/knos-nebius:0.3.30 --platform cpu-d3 --preset 4vcpu-16gb --container-port 8080 --auth token --token
   "$AUTH_TOKEN" --subnet-id <subnet id>` (the quickstart's form). Pass the two keys as container environment variables if the CLI offers it; without them the page
   shows the MOCK run, labelled.
4. Read the URL: `nebius ai endpoint get <id> --format json | jq -r '.status.public_endpoints[]'`. With `--auth token`
   a visitor needs the token: share it with the judges, or check the endpoints docs for an open option first.
5. When the contest is over: `nebius ai endpoint delete <id>`.
