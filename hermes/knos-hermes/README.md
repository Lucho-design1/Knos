# knos-hermes

Hermes keeps one memory per agent. [Knos](https://github.com/drexthealpha/Knos)
keeps one memory per **repo**, shared by every coding agent on the machine —
Hermes, Claude Code, Cursor, OpenCode — and it knows which of them is working
on what right now.

This is Knos as a Hermes `MemoryProvider`.

```bash
pip install knos-hermes
knos-hermes install
```

Then in Hermes: `hermes memory setup` and pick **knos**. Or set it by hand in
`$HERMES_HOME/config.yaml`:

```yaml
memory:
  provider: knos
```

No API key, no server, no model download, no ports. It reads and writes the
same SQLite file the `knos` CLI already uses, so a decision Hermes records is
visible to Claude Code on its next question.

## Why `knos-hermes install` and not just `pip install`

Hermes discovers memory providers by **scanning directories** — bundled ones
in `plugins/memory/<name>/`, and yours in `$HERMES_HOME/plugins/<name>/`. It
does not read pip entry points: `plugins/memory/__init__.py` in hermes-agent
has no `importlib.metadata` call anywhere, though CONTRIBUTING.md mentions
one. So `pip install` alone cannot register anything. `knos-hermes install`
copies the provider into the directory the loader actually scans, and
`knos-hermes where` prints that path without touching anything.

## What Hermes gets

| Tool | What it does |
|---|---|
| `knos_recall` | Search past sessions, commits, `CLAUDE.md`, `AGENTS.md` and decision records. Every result names its source. |
| `knos_remember` | Write one fact into the shared memory, so every other agent has it. |
| `knos_claim` | Say what you are about to change. Other agents are refused answers about it. |
| `knos_done` | Release it. |

Recall is injected before each turn through `prefetch`, so Hermes sees what
the other agents already worked out without being asked to look.

## The part no other provider does

Claim a piece of work and the shared memory stops being the place other agents
find out about it:

```
Withheld. the auth refactor (held by Claude Code) is being worked on right
now, so knos is not the place you find out about it. Ask them, or work on
something else.
```

Not a warning attached to an answer — no answer. It works in the other
direction too: what Hermes claims is withheld from Claude Code and Cursor.
Claims lapse after thirty minutes, and `shutdown()` releases whatever this
session held so a clean exit never leaves the others blocked.

## Not in the Hermes tree, on purpose

hermes-agent's CONTRIBUTING is explicit: *"We are no longer accepting new
memory providers into this repo… PRs that add a new directory under
`plugins/memory/` will be closed with a pointer to publish the provider as
its own repo."* This is that repo.

`hermes-agent` is deliberately **not** a dependency. The tests stub the
`MemoryProvider` ABC instead, mirroring its abstract set, so installing this
never drags the agent in.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

Including the one that matters: `test_nothing_touches_the_network` breaks
`socket.connect`, `bind`, `create_connection` and `getaddrinfo`, then runs
recall, remember, claim, release and shutdown. Every other Hermes memory
provider needs an API key; this one must not open a socket at all.

## Licence

MIT.
