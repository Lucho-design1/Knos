# Knos builds Knos on Nemotron

NVIDIA Nemotron 3 models, served by Nebius Token Factory, write code for Knos. The Knos referee decides what is kept.
Nemotron 3 Ultra explains each refused cheat. Tavily checks where submitted code came from and looks for new ways to
cheat; a new rule enters the referee only if it passes the referee's own test.

The problem: in the public AIDev dataset, 1,119 of 3,736 agent pull requests (30%) that said tests pass had a failing
check at their head commit ([docs/reference/SLOP_AUDIT.md](../../docs/reference/SLOP_AUDIT.md)). A coding agent that
writes code needs a judge it cannot talk round. Here the model is the coder and Knos is the judge.

## Run it

```bash
pip install -e .                     # from the root of this repository
python -m knos.nebius status         # which provider is live, which is MOCK (never prints a key)
python -m knos.nebius demo --out /tmp/knos-nebius --iterations 4
# open /tmp/knos-nebius/panel.html
```

With `NEBIUS_API_KEY` set, every model call goes to Token Factory; with `TAVILY_API_KEY` set, every search goes to
Tavily. Without them, the demo uses MOCK replies:

> **MOCK (synthetic, not a real API response).** The replies are made locally in the documented response shapes, and
> every one carries that label in the JSON and on the panel. The referee's runs are real: the autoresearch referee runs
> each proposed file on sealed synthetic data, and the cheat library screens each proposed diff.

The committed [panel.html](panel.html), [panel.json](panel.json) and [demo-output.txt](demo-output.txt) are one such
MOCK run, made on 14 Oct 2026 with neither key set. Their token counts, latency and cost are MOCK numbers (tokens
estimated at four characters each, costs at the catalog prices below). The decisions (kept, refused) and the scores
come from the real referee on synthetic data.

## How NVIDIA models and Token Factory are used

| step | model or service | what it does | who decides |
|---|---|---|---|
| propose a change | Nemotron 3 Super, `nvidia/nemotron-3-super-120b-a12b`, Token Factory chat completions | the `knos.autoresearch` proposer: reads the task, the current best file and the referee's past decisions (never a hidden score) and returns the whole new file | the autoresearch referee: sealed data, two seeds (the re-run), cheat rules |
| propose a Knos change | Nemotron 3 Super | the `knos self` coder: reads a target from `targets.yml` and its in-scope files, returns one unified diff | `knos self check-pr` rules (trusted core, scope, cheat library); then `knos self run` (sealed tier, daily cap) |
| explain a refusal | Nemotron 3 Ultra, `nvidia/Nemotron-3-Ultra-550b-a55b` | a short paragraph: why each finding is a way to pass without doing the work | nobody: advisory text. The verdict field is copied from the referee and a test proves a lenient explanation cannot change it |
| draft a new cheat rule | Tavily search, then Nemotron 3 Super with `response_format` `json_object` | turns search results into a rule proposal: one pattern, a known-bad diff, a known-good diff, the sources | `knos.nebius.rules_intake`: fires on the bad case, silent on the good case, adds coverage the library lacks; else rejected |
| provenance | Tavily search | searches the best candidate's most distinctive lines; a verbatim hit flags "possible copy" | a person: advisory, never a verdict |
| re-run | Nebius Serverless Jobs, if the operator opts in | `python -m knos.nebius job` creates a job that re-judges the best file on the sealed final set | the same referee code, in the job |

The client is `src/knos/nebius/tokenfactory.py`: the OpenAI-compatible API at `https://api.tokenfactory.nebius.com/v1/`,
`POST chat/completions` with a bearer key from `NEBIUS_API_KEY`, standard library only. Model ids are copied from the
Token Factory model catalog; `GET /v1/models` lists what a live account can call. Prices used for cost (USD per 1M
tokens, input / output, catalog read 14 Oct 2026): Super 0.30 / 0.90, Ultra 1.00 / 3.00. Tavily: 1 credit per basic
search, USD 0.008 per credit on pay-as-you-go. Every source and its date is in
[docs/reference/NEBIUS.md](../../docs/reference/NEBIUS.md).

**Re-runs in this build: local sandbox.** Serverless Jobs are driven by the `nebius` CLI with its own profile and
project id, which this machine does not have; `python -m knos.nebius status` says which backend is in use and why.

## The panel

`panel.html` is one static file with its data inside: tokens per model, latency (p50 and max), cost, cost per
verified improvement (all spend divided by the changes the referee kept), cheats caught, and rules accepted. A zero is
printed as 0; with no kept change, cost per verified improvement is "none".

## Deploy as a Nebius Serverless Endpoint

[Dockerfile](Dockerfile) builds an image that runs the demo once at start and serves the panel on port 8080. The
founder's steps are in docs/reference/NEBIUS.md ("Demo URL").

## Licence

MIT ([LICENSE](../../LICENSE)), like the rest of this repository.
