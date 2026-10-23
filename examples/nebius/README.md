# Knos on Nemotron: a coding agent writes the code, Knos decides if it counts, and the agent gets paid

Agents write, run and test code in Token Factory. Knos is the whole product here: the referee, the payment program, the meter and the invoice that a team running coding agents pays for.

The problem, measured: in the public AIDev dataset, **1,119 of 3,736** agent pull requests (30%) that said tests pass
had a failing check at their head commit, and **6,059 of 8,954** agent pull requests that fail a measured Knos check
were merged anyway ([docs/reference/SLOP_AUDIT.md](../../docs/reference/SLOP_AUDIT.md)). A coding agent needs a judge
it cannot talk round, and the people who pay for its work need to pay only for work that passed.

## The one flow: post a task, the agent codes on Nemotron, the referee judges, the agent is paid

```bash
uv tool install knos          # or: pip install -e .   (from the root of this repository)
python -m knos.nebius flow --out /tmp/knos-flow
# open /tmp/knos-flow/flow.html
```

| step | what happens | where |
|---|---|---|
| 1 post | a team posts the task in [task/TASK.md](task/TASK.md). Knos SEALS its hidden acceptance tests ([task/hidden/](task/hidden/)): the spec hash and the hash of the judging code are fixed before any work starts. With `--wallets DIR` the team funds the bounty, held by `knos_pay` on Solana devnet; the payment program's terms carry the seal hash. | `knos.referee.seal`, `knos.nebius.onchain` |
| 2 code | **Nemotron 3 Super on Token Factory writes `duration.py` and its own pytest tests.** The agent writes the files into the task's repository, **runs** `python -m pytest` there (no key in the environment, a timeout), and sends the failures back to the model, until its own tests pass. | `knos.nebius.agent` |
| 3 pay per check | with `--wallets` the agent pays for one raw Knos check itself: 0.02 test USDC over **x402 v2 `exact`** through the public x402.org facilitator, to Knos's treasury, on devnet | `knos.nebius.onchain`, `knos.money.x402_exact` |
| 4 provenance | **Tavily** searches the agent's most distinctive lines for a public copy (advisory) | `knos.nebius.tavily` |
| 5 referee | the Knos referee judges the agent's code: sealed bundle hash, locked judge hash, the cheat library, the hidden tests the agent never saw, and a re-run that must agree. A refusal gets **Nemotron 3 Ultra**'s explanation (advisory: the verdict is copied, never changed). A scripted cheater (SYNTHETIC, labelled) delivers the same task too: its own tests pass, the referee refuses it. | `knos.referee.works`, `knos.nebius.explain` |
| 6 paid | on a pass, the job pays the agent's wallet. **LABELLED LiteSVM**: `knos_pay` releases money only on a GitHub Actions OIDC token from a signed run of a pinned prove.yml, which a task judged outside GitHub cannot have. The same job (amount, terms, pin) is replayed in LiteSVM with the test builds and paid there. | `knos.nebius.payout` |
| 7 metered | every step is a usage event per team and per agent; the invoice bills only what devnet confirms (the team's first verification is free, then 1.00 USD per verified merge); the dashboard shows verifications, cheats caught, failing merges blocked and "paid and final in N ms" | `knos.money.teams` |

A committed devnet run is in [flow-run/](flow-run/): [flow.json](flow-run/flow.json), [flow.html](flow-run/flow.html)
and the team's usage record [usage.jsonl](flow-run/usage.jsonl) (two runs, labelled internal dogfooding). Its devnet
transactions (the funding of the held money and the x402 check, each finalized; the cluster answered `getAgGenesisCert` with a
certificate, so Alpenglow) are listed in [docs/reference/TEAMS.md](../../docs/reference/TEAMS.md). The model replies in
that run are MOCK (no key on the build machine), and the payout is LiteSVM; both are labelled in the files.

## Setup

- Python 3.11+. `uv tool install knos` or `pipx install knos`, or from a checkout `pip install -e .`
- `NEBIUS_API_KEY`: a Token Factory key (tokenfactory.nebius.com). With it, every model call goes to Token Factory.
- `TAVILY_API_KEY`: a Tavily key. With it, every provenance search goes to Tavily.
- `python -m knos.nebius status` says which provider is live and which is MOCK. It never prints a key.
- Devnet (optional): a folder with `team.json`, `agent.json` (Solana keypair files) and `mint.json` (the team's test
  mint), the team holding devnet SOL and test units: `python -m knos.nebius flow --wallets DIR`.

Without the keys every model and search reply is MOCK:

> **MOCK (synthetic, not a real API response).** The replies are made locally in the documented response shapes, and
> every one carries that label in the JSON and on the page. The agent's test runs, the referee, and the devnet
> transactions are real in every mode.

## How NVIDIA models and Token Factory are used

| step | model or service | what it does | who decides |
|---|---|---|---|
| write, run and test code | Nemotron 3 Super, `nvidia/nemotron-3-super-120b-a12b`, Token Factory chat completions | the coding agent of the flow: writes the implementation and its tests as whole files, reads its own pytest output, fixes what fails (`knos.nebius.agent`) | the Knos referee, on sealed tests the model never sees |
| propose a change | Nemotron 3 Super | the `knos.autoresearch` proposer: reads the task, the current best file and the referee's past decisions (never a hidden score) and returns the whole new file | the autoresearch referee: sealed data, two seeds (the re-run), cheat rules |
| propose a Knos change | Nemotron 3 Super | the `knos self` coder: reads a target from `targets.yml` and its in-scope files, returns one unified diff | `knos self check-pr` rules (trusted core, scope, cheat library); then `knos self run` (sealed tier, daily cap) |
| explain a refusal | Nemotron 3 Ultra, `nvidia/Nemotron-3-Ultra-550b-a55b` | a short paragraph: why each finding is a way to pass without doing the work | nobody: advisory text. The verdict field is copied from the referee and a test proves a lenient explanation cannot change it |
| draft a new cheat rule | Tavily search, then Nemotron 3 Super with `response_format` `json_object` | turns search results into a rule proposal: one pattern, a known-bad diff, a known-good diff, the sources | `knos.nebius.rules_intake`: fires on the bad case, silent on the good case, adds coverage the library lacks; else rejected |
| provenance | Tavily search | searches the agent's most distinctive lines; a verbatim hit flags "possible copy" | a person: advisory, never a verdict |
| re-run | Nebius Serverless Jobs, if the operator opts in | `python -m knos.nebius job` creates a job that re-judges a file on the sealed final set | the same referee code, in the job |

The client is `src/knos/nebius/tokenfactory.py`: the OpenAI-compatible API at `https://api.tokenfactory.nebius.com/v1/`,
`POST chat/completions` with a bearer key from `NEBIUS_API_KEY`, standard library only. Model ids are copied from the
Token Factory model catalog; `GET /v1/models` lists what a live account can call. Prices used for cost (USD per 1M
tokens, input / output, catalog read 14 Oct 2026): Super 0.30 / 0.90, Ultra 1.00 / 3.00. Tavily: 1 credit per basic
search, USD 0.008 per credit on pay-as-you-go. Every source and its date is in
[docs/reference/NEBIUS.md](../../docs/reference/NEBIUS.md).

## Who pays, how much

Starting prices from [config/fees.yaml](../../config/fees.yaml) (decided 14 Oct 2026; nobody pays them yet, devnet
revenue is 0): **1.00 USD per verified merge** for a team (the first verification free), **0.02 USD per raw agent
check** over x402, **5% bounty fee**, verified task packages for labs split **maintainer 90 / Knos 10**. Paid in USDC
on Solana. The prices and the revenue model (labelled a model): [docs/reference/TEAMS.md](../../docs/reference/TEAMS.md).

## The other demo: Knos builds Knos on Nemotron

`python -m knos.nebius demo --out /tmp/knos-nebius` runs Nemotron as the autoresearch proposer and as the `knos self`
coder, with refusals explained by Ultra and a new cheat rule drafted from Tavily results. The committed
[panel.html](panel.html), [panel.json](panel.json) and [demo-output.txt](demo-output.txt) are one MOCK run made on
14 Oct 2026 with neither key set: their token counts, latency and cost are MOCK numbers; the decisions come from the
real referee on synthetic data.

**Re-runs in this build: local sandbox.** Serverless Jobs are driven by the `nebius` CLI with its own profile and
project id, which this machine does not have; `python -m knos.nebius status` says which backend is in use and why.

## Deploy as a Nebius Serverless Endpoint

[Dockerfile](Dockerfile) builds an image that runs the flow and the demo once at start and serves them on port 8080
(the flow's page is the index).

## Licence

MIT ([LICENSE](../../LICENSE)), like the rest of this repository; GitHub shows "MIT License" in the repository's About.
