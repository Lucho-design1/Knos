# Knos for Hermes Agent

Hermes Agent (Nous Research) can use Knos three ways: as a skill, as an MCP server, and as a plugin. Each gives the
agent the same habit: run `knos verify` before a pull request, never open one where the repository's AI policy bans
it, attach the signed receipt, disclose AI use. The Knos referee also serves as the judge for Hermes self-evolution
(GEPA), and Knos sealed tasks are exported as an Atropos environment. Everything here is devnet or demo: nothing in
this page moves real money, and the example tasks are synthetic.

## Sources

Every Hermes, GEPA and Atropos interface used here was read in the source, at these commits (13 Oct 2026):

| What | Where |
| --- | --- |
| Hermes Agent (release v0.21.7, 12 Oct 2026; the repository's tags are date-based, so the code is cited by commit) | [NousResearch/hermes-agent@8f817911](https://github.com/NousResearch/hermes-agent/tree/8f817911723e3ec13e7f47fc022fdcc9e2149354) |
| Skills Guard: `scan_skill`, `should_allow_install`, `INSTALL_POLICY`, `THREAT_PATTERNS`, structural limits | `tools/skills_guard.py` (SCANNER_VERSION `skills-guard-v10`) |
| Plugin scan: `scan_plugin` (the skills engine with plugin rules) | `tools/plugin_guard.py` (`plugin-guard-v11`), `tools/plugin_guard_context.py` |
| SKILL.md format, `metadata.hermes`, `required_environment_variables`, taps, well-known endpoints | `website/docs/user-guide/features/skills.md` |
| Skill name and description limits (64 / 1024), lint rules | `tools/skills_tool_plugin.py`, `tools/skill_linter.py` |
| Well-known index: `GET <base>/.well-known/skills/index.json` -> `{"skills": [{"name", "description", "files"}]}` | `tools/skills_hub_sources.py` (`WellKnownSkillSource`) |
| Plugin manifest fields (`name`, `version`, `provides_tools`, `python_dependencies`, ...) | `hermes_cli/plugins_manifest.py` (`PluginManifest`) |
| `ctx.register_tool(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, description="", emoji="", override=False)` | `hermes_cli/plugins.py` (`PluginContext.register_tool`) |
| Handler contract `handler(args: dict, **kwargs) -> str` (JSON, never raises) | `website/docs/developer-guide/plugins/index.md`, `tools/registry.py` (`dispatch`) |
| Entry-point group `hermes_agent.plugins`, value `package:register` | `hermes_cli/plugins_discovery.py` (`ENTRY_POINTS_GROUP`), plugins guide |
| `mcp_servers` keys: `command`, `args`, `env`, `url`, `headers`, `timeout`, `tools.include` / `tools.exclude` | `website/docs/user-guide/features/mcp.md` |
| GEPA metric `skill_fitness_metric(example, prediction, trace=None) -> float`, passed to `dspy.GEPA(metric=...)` | [NousResearch/hermes-agent-self-evolution@0a929e3a](https://github.com/NousResearch/hermes-agent-self-evolution/tree/0a929e3aa20e15cf04dc7c28492a7d41a5139125) `evolution/core/fitness.py`, `evolution/skills/evolve_skill.py` |
| Atropos `BaseEnv` (abstract `get_next_item`, `evaluate`; `collect_trajectories(item) -> (ScoredDataGroup, backlog)`; `config_init`; `cli()`), `BaseEnvConfig`, `ScoredDataGroup`, `tokenize_for_trainer` | [NousResearch/atropos@296a0bc5](https://github.com/NousResearch/atropos/tree/296a0bc55760e43b9c0743c052f8d6c2732606d1) `atroposlib/envs/base.py`, `atroposlib/utils/tokenize_for_trainer.py`, `environments/gsm8k_server.py` |

## 1. Skill: `hermes/knos/`

`hermes/knos/SKILL.md` (agentskills.io format: `name`, `description`, `version`, `author`, `license`, `platforms`,
`metadata.hermes.{tags, category, requires_tools}`, `required_environment_variables`), `scripts/knos-verify.sh`
and `references/` (the receipt, how the AI policy is read, the tools).

Install it any of three ways:

```bash
hermes skills install drexthealpha/Knos/hermes/knos                       # straight from this repository
hermes skills install well-known:https://drexthealpha.github.io/Knos/.well-known/skills/knos   # from the site
hermes skills tap add drexthealpha/knos-skills                            # a tap, once published (founder decision)
```

- **Well-known endpoint.** `web/.well-known/skills/index.json` and a copy of the skill's files under
  `web/.well-known/skills/knos/`, written by `python hermes/publish.py well-known`; `python hermes/publish.py check`
  (and tests/test_agents_skills.py) fails when the copy and `hermes/knos/` differ. The site build copies `web/` as it
  is, dot-folders included (scripts/build_site.sh).
- **Tap.** A tap is a repository with `skills/<name>/SKILL.md`. This repository keeps its Hermes skill in `hermes/`
  (a root `skills/` folder would become part of the Gemini CLI extension, which tests/test_install_routes.py
  forbids), so the tap is a separate repository: `python hermes/publish.py tap OUT` writes its layout into `OUT`.

## 2. MCP server (stdio and HTTP)

Add one of these to `mcp_servers` in your Hermes config (`~/.hermes/config.yaml`). Knos never writes that file for
this; `knos init --host hermes --global` writes a stdio block with only the reading tools, marked so it can be
removed.

```yaml
# stdio: Hermes starts the server
mcp_servers:
  knos:
    command: "knos"            # or "uvx" with args ["knos", "mcp"]
    args: ["mcp"]
    timeout: 900               # knos_verify runs the repository's tests twice
```

```yaml
# HTTP: start the server yourself first:  KNOS_MCP_HTTP_TOKEN=<a long random string> knos mcp --http 8808
mcp_servers:
  knos:
    url: "http://127.0.0.1:8808/mcp"
    headers:
      Authorization: "Bearer ${KNOS_MCP_HTTP_TOKEN}"
    timeout: 900
```

`knos mcp --http [HOST:]PORT` (src/knos/mcp_http.py) is the same server over MCP's Streamable HTTP transport: `POST`
answers with `application/json`, a notification gets `202`, `GET` is `405` (no server-to-client stream), no session
id. It binds to 127.0.0.1 unless given another host, refuses an `Origin` that is not loopback, and with
`KNOS_MCP_HTTP_TOKEN` set refuses a request without that bearer token.

The server's two tools for this: `knos_verify` (path, base, tests, runs, agent, out) and `knos_receipt` (file).
`knos_verify` runs the repository's test command on your machine: it is marked not read-only, Knos never puts it on
an allowlist (so `knos init --host hermes --global` leaves it out of `tools.include`; add it yourself if you want
it), and over HTTP it is served only when `KNOS_MCP_HTTP_TOKEN` is set. `--http` on an address other than loopback
refuses to start without that token.

## 3. Plugin

`pip install knos` puts this in the package's metadata (pyproject.toml):

```toml
[project.entry-points."hermes_agent.plugins"]
knos = "knos.hermes_plugin:register"
```

Hermes finds it by the group name and calls `register(ctx)`, which registers four tools in the toolset `knos`
(src/knos/hermes_plugin.py):

| Tool | What it does | Sends |
| --- | --- | --- |
| `knos_verify` | `knos verify` on a committed change: AI policy at the base, cheat checks, tests twice in a throwaway clone, signed receipt, `pr_markdown` | nothing |
| `knos_receipt` | checks a receipt's shape, digest and ed25519 signature | nothing |
| `knos_bounty_claim` | a bounty's amount and terms (`knos_bounty`), the `/knos take` comment (`knos_take`), and the steps to be paid | nothing |
| `knos_outcome_check` | whether an outcome measurement drifted from what was funded (spec hash, window, salt, control share, measurement code, data hashes): the referee's `cheats.scan_outcome` when installed, else the same comparisons locally | nothing |

When the money engine is installed (knos.money.agent), its quote and plan tools are registered too. A directory
plugin is also provided: copy `hermes/plugin/knos/` (plugin.yaml and an `__init__.py` that imports the same
`register`) into the plugins folder of your Hermes home.

## Skills Guard result

Hermes scans every skill from a community source (a tap, a well-known endpoint, a GitHub path) with Skills Guard,
and blocks `caution` and `dangerous`; plugins get the same engine with plugin rules. Measured once, 13 Oct 2026, with
the scanners at hermes-agent@8f817911 run from a source checkout in WSL. The `scan_skill` rows are re-checked by
every test run (below); the two `scan_plugin` rows are not: that scanner also needs `tools/plugin_guard_context.py`,
which the repository does not vendor, so those counts are a one-time measurement at the version of the code that day.

| Scanned | Scanner | Verdict | Findings |
| --- | --- | --- | --- |
| `hermes/knos/` (the Hermes skill) | `scan_skill(..., source="drexthealpha/Knos")` | safe, allowed | 1 medium: `hardcoded_ip_port` on the loopback address `127.0.0.1:8808` in references/tools.md |
| `plugin/skills/knos-verify/` (Claude Code) | `scan_skill` | safe, allowed | 1 low: `allowed_tools_field` (standard frontmatter) |
| `integrations/skills/openclaw/knos-verify/` | `scan_skill` | safe, allowed | none |
| `web/.well-known/skills/knos/` (the site's copy) | `scan_skill` | safe, allowed | the same 1 medium as `hermes/knos/` |
| `hermes/plugin/knos/` | `scan_plugin` | safe | none |
| the plugin with its code (hermes_plugin.py, verify/, mcp_http.py, the GEPA judge, the Atropos env) | `scan_plugin` | safe | 7 medium `python_subprocess` (git, the test run, the sealed-task check) and 2 low `hardcoded_ip_port` (the loopback default) |

The repository keeps the skill scanner, unmodified, as `tests/data/hermes_skills_guard.py.txt` (MIT, Nous Research),
and tests/test_hermes_guard.py runs it offline on every skill, on the plugin folder and on its code (the code with the
stricter skill rules: the test asserts verdict safe with no high or critical finding, not the plugin counts above),
and on a hostile skill as a control, which it must block.

## 4. The referee as GEPA's judge

Hermes self-evolution evolves a skill's text with DSPy GEPA, scored by a metric. Its shipped metric is a keyword
overlap with an LLM judge for the expensive pass: it measures how a response looks, so evolution can climb by
looking right. `hermes/gepa/knos_judge.py` offers a metric with the same call shape that measures whether the work is
right, against tests the candidate never saw:

```python
from hermes.gepa.knos_judge import make_metric
metric = make_metric(tasks_dir="path/to/sealed/tasks")     # each example names a sealed task: example.knos_task
optimizer = dspy.GEPA(metric=metric, ...)
```

The candidate's output must hold a unified diff; it is applied to a copy of the task's base and judged by
`knos.referee.judge_candidate(base, pr, seal)` (the REFEREE API: sealed hidden tests whose hash was committed before
the work, the locked judge hash, the cheat library, a re-run). A task without a seal, or an install without the
referee, is not scored (0.0, "unsealed"). `allow_unsealed=True` scores such a task with a labelled fallback (the local
cheat rules, then the task's check command, which must exit 0 and write a test report with no failure): that fallback
is NOT tamper-proof, because the candidate's code runs in the same process as the check and can forge a report, so it
is for the synthetic demo only, never for real evolution. Score 1.0 when the sealed checks pass, else 0.0; a
cheat (edited tests, CI or fixtures, files out of scope, ...) is never worth more than an honest failure and its
category is named in the feedback (`dspy.Prediction(score, feedback)` when DSPy is present, for GEPA's reflection).
`scale="raw"` keeps the referee's own reward (1.0 / 0.0 / -1.0). Hidden test text never appears in feedback.

## 5. Atropos environment

`hermes/atropos/knos_env.py` defines `KnosSealedEnv(BaseEnv)` (`name = "knos_sealed"`) when atroposlib is installed:
`get_next_item` cycles the sealed tasks, `collect_trajectories` asks the policy for `group_size` answers to the
task's prompt (the prompt only, never the bundle), judges each with the referee, and returns a `ScoredDataGroup` of
`tokenize_for_trainer` tokens and masks with the referee's reward as each score (1.0 passed, 0.0 failed, -1.0 a
cheat); `evaluate` reports `eval/knos_pass_rate`. Run it as any Atropos environment:
`python hermes/atropos/knos_env.py serve` (set `KNOS_ATROPOS_MODEL` and `KNOS_ATROPOS_BASE_URL`). The two tasks in
`hermes/atropos/tasks/` are synthetic and labelled so, and they carry no seal: `setup` refuses them unless the
config sets `allow_unsealed` (then they are scored by the forgeable fallback above: a demo of the plumbing, not of
an ungameable reward). A sealed task is a folder with `task.json` (with the referee's `seal`) and `base/`, the hidden
bundle at `base/.knos/acceptance/<issue>/` (knos.verify.sealed). Demo only: no reward here is money.

## Founder decisions

- Publish the tap repository (`python hermes/publish.py tap OUT`, then push OUT as e.g. drexthealpha/knos-skills).
- Publish the plugin on PyPI: it ships inside the `knos` package (the entry point above) from the next release; no
  separate package is needed.
- Submit the plugin to the Hermes plugin catalog (`plugin-catalog/<name>.yaml` in hermes-agent, a human-reviewed PR
  pinned to a 40-character commit SHA).
- Ask for `TRUSTED_REPOS` status in Hermes's Skills Guard (a Hermes core PR); until then Knos installs as community.
