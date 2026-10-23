# Knos Gate for maintainers

**Checking outside work costs more than producing it. Knos checks it for you, against tests the author cannot see.**

## What happens on every outside pull request

1. Knos runs your hidden tests (a repository secret, or a private repository the author cannot read) in a pinned
   workflow.
2. Before any of the pull request's code runs, it applies the cheat rules: edited tests, files outside the scope you
   set, tampered data, edited workflows.
3. It posts one status check and one short comment: pass or fail, which rule, and a re-run link. On a failure it labels,
   comments or closes, as your `.knos/gate.yml` says.

It works alongside who-sent-it filters (Vouch, collaborator-only, pull request caps). Those judge who sent the work;
Knos judges whether the work is correct. A passing Knos check can be a bypass signal, if you opt into that.

## What it costs and what it never does

- Free for public repositories. No wallet, no token and no held money are needed for the check.
- It never shows a hidden test's contents in a log, comment or receipt.
- It never opens a pull request on your repository, and never pays anyone unless you fund a bounty.

## Optional

- **Bounties**: fund an issue; the first pull request that passes the hidden tests and that you merge is paid
  automatically (test USDC on devnet today). Spam claims are closed by the Gate. The fee is in the one fee config.
- **Task packages**: export a merged issue + fix as a sealed, verified task ([TASK_PACKAGES.md](../reference/TASK_PACKAGES.md)).
  Only with your opt-in, within your licence. Selling them is not offered today.
- **Research**: add `knos.yml`; a clean reproduction earns a "Reproduced by Knos" badge, and a contested one comes to
  you privately ([REPRODUCED.md](../reference/REPRODUCED.md)).

## The measured problem

Of the agent pull requests that said their tests pass and whose last commit has a finished CI result, 1,119 of 3,736 (30%) had a failing check (AIDev v4, 71,677 agent pull requests; [SLOP_AUDIT.md](../reference/SLOP_AUDIT.md)).

Install: [INSTALL.md](INSTALL.md).
