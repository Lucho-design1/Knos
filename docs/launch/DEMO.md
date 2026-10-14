# The 60-second demo

Three scenes on a test repository of the owner's (`drexthealpha/knos-e2e`, or a new private `drexthealpha/knos-v0329-*`
test repository). Knos Gate is on, with a hidden test suite the pull request's author cannot read. Money is test USDC
on Solana devnet and has no value. Record the screen; say the lines in quotes.

## 0:00 to 0:05: the problem

On screen: the repository's open pull requests.

> "Maintainers are closing their doors to outside pull requests, because checking work now costs more than writing it.
> Knos checks the work itself, against tests the author never saw."

## 0:05 to 0:25: a bad AI pull request is refused

1. An agent's pull request "fixes" the issue by editing the test so it passes.
2. The Knos Gate check runs. It fails in seconds, before any of the pull request's code runs, with the rule that fired:
   `test_edited`.
3. The repository's setting is `auto-close`: Gate closes the pull request with one short comment naming the rule and a
   re-run link.

> "This one changed the test. Knos refused it and closed it. No human read it."

## 0:25 to 0:45: a good pull request passes with a receipt

1. A second pull request fixes the code and touches no test.
2. The Gate check runs the hidden tests in the pinned workflow: pass. One comment: the receipt link and the badge.
3. Open the receipt page: spec hash, the number of hidden tests (never their contents), cheat checks passed, the
   runner, the re-run result. Run `knos verify` on it: the signature checks.

> "This one fixed the bug. The receipt says which hidden tests ran and that nothing was tampered with. Anyone can check it."

## 0:45 to 0:58: the bounty is paid on devnet

1. The issue carried a bounty in escrow on devnet. The maintainer merges the passing pull request.
2. The payment lands: open `2MbUhEUKdzLvyHe4WEd8cLqv1HGcKV91GGTNqF8y8EWN4jYTAw36n2nvsLBTsCw8ep9BBZLs3279TaN9Zobt9h1x` in the Solana explorer (devnet). The fee goes to the treasury account
   named in the one fee config.

> "Merged, and paid automatically. Test USDC on devnet; the maintainer never needed a wallet to use the check."

## 0:58 to 1:00: the claim

> "Three in ten agent pull requests that said their tests pass had a failing check. Turn on Knos Gate for your repository."

(The number: 1,119 of 3,736, [SLOP_AUDIT.md](../reference/SLOP_AUDIT.md).)

(Say "in two clicks" only once the GitHub App is registered and its install link exists; registering it is a
founder decision. Until then the install is the Action in INSTALL.md.)

Before recording: run the three scenes once and check each step against what is on screen. If any step does not
happen exactly as written, fix the script, not the recording.
