# Knos as an A2A agent: other platforms hire it as their judge

[A2A](https://github.com/a2aproject/A2A) 1.0.0 (`docs/specification.md`, `specification/a2a.proto`, read 14 Oct 2026) is
how one agent finds another and hands it a task. An agent publishes an Agent Card at
`https://{server_domain}/.well-known/agent-card.json`; the required fields are `name`, `description`,
`supportedInterfaces` (`url`, `protocolBinding`, `protocolVersion`), `version`, `capabilities`, `defaultInputModes`,
`defaultOutputModes` and `skills` (`id`, `name`, `description`, `tags`).

`python -m knos.a2a serve [--port 8765] [--url PUBLIC_URL] [--allow-verify]` serves both the card and the JSON-RPC
endpoint (`/a2a/v1`) from one process, on 127.0.0.1 unless told otherwise, so the card never names an endpoint that
is not running. `python -m knos.a2a card URL` prints the card for an endpoint.

The card of a default local run is
[`examples/a2a/.well-known/agent-card.json`](../../examples/a2a/.well-known/agent-card.json); a test keeps it equal
to what the server serves. It also carries `url` and `preferredTransport` where A2A 0.3.0 cards named the endpoint;
the methods answered are 1.0's.

| A2A | Knos |
|---|---|
| `SendMessage` with a `data` part `{"skill": ..., ...}` or a pull request URL in a `text` part | runs the skill; answers a `Task` in `TASK_STATE_COMPLETED` with one artifact (the tool's JSON), `TASK_STATE_FAILED` with the reason, or `TASK_STATE_REJECTED` |
| skill `verify` | `knos_verify`: cheat checks and two re-runs of the tests in a throwaway clone, a signed receipt. It runs code on this machine, so it is refused unless the server was started with `--allow-verify` |
| skill `check-pr` | `knos_check_pr`: does a public pull request's description agree with GitHub's record of its tests (read-only) |
| skill `find-work` | `knos_find_work`: open, funded work orders and the terms that decide payment (read-only) |
| `GetTask`, `ListTasks`, `CancelTask` | as specified; a finished task cannot be cancelled (`-32002`) |
| errors | `-32001` task not found, `-32004` unsupported method, `-32005` content not understood, `-32009` an `A2A-Version` this agent does not speak |

Not done, and why: there is no hosted Knos A2A endpoint. Running one behind HTTPS on a domain Knos controls (and
deciding whether `verify` is offered there) is the founder's decision; until then the card describes a local agent.
Streaming and push notifications are declared off.

Tests: `tests/test_mcp_ext_a2a.py`.
