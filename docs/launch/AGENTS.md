# Knos for agents

**Run Knos before you open a pull request, and attach the receipt.**

1. Read the repository's AI policy (`AI_POLICY.md`, `CONTRIBUTING.md`). If it bans AI pull requests, do not open one.
   If it asks you to disclose AI use, disclose it.
2. Fix the issue. Do not edit tests, workflows or files outside the issue's scope: the Gate refuses those before any
   test runs.
3. Run `knos verify` on your branch. On your machine it runs the repository's own public tests, and the receipt says
   "public tests only". The hidden tests run only in the repository's Knos Gate check, on the pull request, where you
   cannot read them.
4. Open the pull request with the receipt link. Maintainers can check it in one click; a passing receipt is evidence,
   not a promise.

The same check is an MCP tool, a Claude Code skill, a Hermes skill and plugin, and an OpenClaw skill
([docs/reference/AGENTS.md](../reference/AGENTS.md)).

## Paid work

Funded issues pay the author of the merged pull request that passes the hidden tests (test USDC on devnet today).
`knos work list` shows open funded work.

## Why it matters

Of the agent pull requests that said their tests pass and whose last commit has a finished CI result, 1,119 of 3,736 (30%) had a failing check (AIDev v4, 71,677 agent pull requests; [SLOP_AUDIT.md](../reference/SLOP_AUDIT.md)).

Pull requests that fix a real issue and pass the maintainer's own tests are the ones that get merged.
