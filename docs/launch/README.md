# Launch kit (v0.3.29)

Four pages for the launch. Every number in them comes from a run in this repository; the one that does not exist yet
is a placeholder that the integration step fills from the measured slop audit, and nothing else fills it.

| page | for |
|---|---|
| [DEMO.md](DEMO.md) | the 60-second demo script: a bad AI pull request refused, a good one passing with a receipt, a bounty paid on devnet |
| [INSTALL.md](INSTALL.md) | installing Knos: the command, the Gate for a repository, the agent skill |
| [MAINTAINERS.md](MAINTAINERS.md) | one page for maintainers: what Knos Gate checks, what it costs, what it never does |
| [AGENTS.md](AGENTS.md) | one page for agents and the people who run them: get a receipt before opening a pull request |

## Placeholders (filled at integration, never by hand)

| placeholder | filled from |
|---|---|
| `{SLOP_NUMBER}` | FILLED: the slop audit's measured result (docs/reference/SLOP_AUDIT.md): 1,119 of 3,736 agent pull requests that said tests pass had a failing check on their last commit. The hidden-test measure (did the attempt pass the tests of the fix finally merged) is NOT measured yet |
| `{GATE_APP_INSTALL_URL}` | NOT FILLED: the App is not registered (a founder decision); the pages say so and point to the Action install in INSTALL.md |
| `{DEMO_BOUNTY_TX}` | FILLED: 2MbUhEUKdzLvyHe4WEd8cLqv1HGcKV91GGTNqF8y8EWN4jYTAw36n2nvsLBTsCw8ep9BBZLs3279TaN9Zobt9h1x (devnet, drexthealpha/knos-e2e#273, own wallets, test tokens) |

Rules these pages keep: no number without its source beside it; devnet money is test USDC and says so; no comparison
with any other contest entry; nothing claims an audit, a customer or a pilot that does not exist.
