# Knos Gate: the GitHub App

Not registered. Registering it is the founder's step: see
[docs/reference/PR_GATE.md](../docs/reference/PR_GATE.md#register-the-app).

- `app-manifest.json`: the App manifest (permissions: checks write, pull requests write, issues write, actions write,
  contents read, metadata read; events: pull_request, workflow_run, check_run).
- `server.py`: the webhook server. The logic is `knos.gate.app` (tests: `tests/test_gate_app.py`).
- `knos-gate.yml`: the workflow a repository adds for App mode (the App dispatches it; it posts nothing itself).

The App owns the one check run ("Knos Gate") and the one comment. Without the App, the Action alone
(`actions/gate`) gives the same check and comment.
