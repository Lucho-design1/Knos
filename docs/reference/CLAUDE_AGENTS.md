# Claude agents on Knos tasks, and Knos judging them

Three pieces, all built and tested with synthetic fixtures; running any of them needs `ANTHROPIC_API_KEY` (or another
credential the Anthropic SDKs resolve), which this build does not have.

## Claude Agent SDK: one of many parallel attempts, stopped at the source when it cheats

`knos.claude.agent_sdk` (sources: [Agent SDK, Python](https://code.claude.com/docs/en/agent-sdk/python) and
[hooks](https://code.claude.com/docs/en/agent-sdk/hooks), read 14 Oct 2026). An attempt runs with
`claude_agent_sdk.query(prompt=..., options=ClaudeAgentOptions(...))`: the Knos MCP server over stdio (`{"knos":
{"type": "stdio", "command": "knos", "args": ["mcp"]}}`) and a `PreToolUse` hook,
`HookMatcher(matcher="Write|Edit|MultiEdit|NotebookEdit|Bash", hooks=[guard])`.

The guard returns `permissionDecision: "deny"` for any write to tests, fixtures, `conftest.py`, CI configuration,
lock files and sealed Knos files, and for shell commands that would write to them; running the tests is allowed.

"If any hook returns deny, the operation is blocked regardless of other hooks." `python -m knos.autoresearch run TASK
--proposer sdk:claude` uses it as a proposer (it needs the `claude-agent-sdk` package and the agent's own key).

## Claude Managed Agents: the platform's grader says "satisfied", Knos decides "paid"

`knos.claude.managed` (sources: the Managed Agents outcomes and Python pages, beta header
`managed-agents-2026-04-01`, read 14 Oct 2026). An agent is created once (`agent_spec()`), each attempt is a session
kicked off with one `user.define_outcome` event whose rubric holds only the task's public criteria. The platform's
grader runs "in a separate context window" and ends with `satisfied`, `needs_revision`, `max_iterations_reached`,
`failed` or `interrupted`.

`run(...)` follows the stream to the documented idle gate, and only when the grader said `satisfied` downloads
`/mnt/session/outputs/` and runs Knos's own judge on them. `Run.payable` is true only when Knos accepted; a satisfied
session that Knos refuses pays nothing. The sealed checks never enter the session.

## Where Knos calls a model: structured outputs and prompt caching

`knos outcome draft --llm` (the user's own key) now asks Claude (`claude-opus-5-5`) for a JSON object fixed by a schema
(`output_config.format` with `type: json_schema`, no beta header; `DRAFT_SCHEMA` in `src/knos/outcomes/draft.py`): only
the fields a model may decide (title, metric name, formula, direction, lift, id and time columns, the tiers'
thresholds).

The parties, the escrow, the control group's salt, the bootstrap and the price cannot come back changed, because they
are not in the answer. The fixed instructions are the cached prefix (`cache_control: {type: ephemeral}` on the system
block); the goal and the buyer's rows come after it.

A prefix under the model's minimum (512 tokens for Claude Opus 5.5, per the prompt-caching guide) is silently not
cached, so the instructions carry worked examples that also make the drafts better. Refusal fallback stays on
(`fallbacks: "default"`).

The other model calls in Knos go to Nebius Token Factory (Nemotron, an OpenAI-compatible API; [NEBIUS.md](NEBIUS.md)),
whose structured-output and caching parameters are that provider's, not these.

Tests: `tests/test_claude_agents_v34.py`.
