# Install

## The command (one line)

```
pip install knos && knos init
```

`knos init` sets Knos up with the coding agents it finds on the machine ([START.md](../START.md)).

## Knos Gate for a repository

Once the GitHub App is registered (a founder decision, not done yet), it is two clicks:

1. Open the Knos Gate App's install page (it exists once the App is registered).
2. Choose the repository and press Install.

Free for public repositories. Then commit `.knos/gate.yml` to say which hidden test suite to run, which paths a pull
request may change, and what to do on a failure (label, comment, or close). The GitHub App is built but not yet
registered: registering it, its name and its Marketplace listing are founder decisions. Until then the same check runs
as a GitHub Action from the repository (docs/reference/GATE.md once Gate's page lands).

## A research repository

Add `knos.yml` and run `knos reproduce .` ([docs/reference/REPRODUCED.md](../reference/REPRODUCED.md)).

## For maintainers who want to export tasks

`knos taskpack export owner/repo#PR --repo-dir CLONE --opt-in` ([docs/reference/TASK_PACKAGES.md](../reference/TASK_PACKAGES.md)).
