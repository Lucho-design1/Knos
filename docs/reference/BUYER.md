<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Post a task as a buyer

**In plain words.** You write what you want and keep a few tests to yourself. Knos posts the task, locks in the tests by their hash, and tells you the exact command that puts your money on it. When work comes in, the same tests judge it, and the worker never sees them.

1. Write the spec.
2. Keep the hidden tests outside every repository.
3. `knos task post`: the issue, the seal and the funding command.
4. `knos fund-wallet`: the money is held until the proof passes.
5. `knos referee works`: the sealed tests judge the delivery.
*Five steps from a spec to a verdict; only step 4 moves money.*

This page was written while Knos bought its own 0.3.31 work as its first customer (internal dogfooding, devnet test
money, labelled so and kept out of every public number). Every limit below is one we hit.

## The one command

```bash
knos task post spec.md --tests ~/hidden/my-task --repo OWNER/NAME --amount 20 --days 3 \
    --mint <your test mint> --keypair ~/wallet.json            # prints every step, sends nothing
knos task post spec.md ... --send                               # opens the issue and posts the seal, with gh, as you
```

It does, in order:

1. checks the spec: its first heading becomes the issue title, and a `/knos fund` line is refused (in a repository
   that runs the Knos workflow, opening the issue would fund it from the faucet instead of your wallet);
2. checks the hidden tests: a warning when the folder sits inside a git repository (a worker may read it) or is not
   black-box (`knos accept init` makes a black-box bundle from a reference program);
3. seals them with `knos referee seal`: the bundle's hash and the hash of the judging code that will judge it;
4. with `--send`, opens the issue and posts the seal as a comment, and writes the seal file next to the tests;
5. prints the funding command, `knos fund-wallet OWNER/NAME#N AMOUNT ...`, and the fee, before anything is funded:
   the program takes 0.30% of the amount, at least 0.05, at payout; Knos's decided 5% bounty fee includes it, and its
   rest is invoiced off chain (config/fees.yaml);
6. prints the judging command, `knos referee works --base ... --pr ... --seal ... --hidden ...`.

Money moves only when you run the printed `knos fund-wallet` yourself.

## Which seal

| command | for |
|---|---|
| `knos referee seal` (used by `knos task post`) | a buyer's new task: hidden tests you keep, judged by `knos referee works` |
| `knos gate seal` | a maintainer's Gate on outside pull requests: the tests go into the repository secret `KNOS_GATE_HIDDEN` |
| `knos taskpack export` | a merged fix turned into a sealed package after the fact |

## Before you post, and when work arrives as a patch

```bash
knos task calibrate --tests ~/hidden/my-task --base <unchanged tree> --reference <your own solution's tree>
knos task judge --seal ~/hidden/seal-N.json --hidden ~/hidden/my-task --commit <base commit> --patch work.patch
```

- `calibrate` judges your hidden tests twice before they are sealed in public, cheat rules off: the unchanged base must
  fail them (or they would pay for no work) and your own solution must pass them (or they would refuse honest work).
  Exit 1 says which. Buying v0.3.34, it caught two defects in our own bundles before any worker saw a seal.
- The judge takes `pyproject.toml`, `setup.cfg`, `pytest.ini`, `tox.ini` and every `conftest.py` from the BASE, so a
  hidden test that reads them sees the base's copy, never the delivered one (a version bump, a new dependency).
  `knos task post` and `calibrate` warn when a bundle names one of them.
- `judge` builds the base (`git archive` of the commit) and the delivered tree (the patch applied with `git apply`),
  then runs `knos referee works` on them.
- A `/knos take` reservation never outlasts the held money: `knos fund-wallet --days 3` reserves for 3 days at most.

## What is not there yet

- **Payment needs GitHub Actions.** Held money pays only on a signed run of the pinned `prove.yml` on a merged pull
  request. Work delivered as a patch, or in a repository without Actions minutes, cannot be paid by the program; it
  goes back to the funder at the deadline. Our own 0.3.31 payouts were shown in LiteSVM, labelled so.
- **The seal is not in the payment program.** `knos fund-wallet` locks check names and paths; the seal's hash is public on the
  issue, not part of the on-chain terms.
- **A document-only delivery is refused** by the cheat rule `no_source_change`: judge a report together with a
  script, or wait for a document kind of seal.
- **Hidden means kept apart.** Nothing encrypts the bundle for the referee alone; keep it on a machine the worker
  cannot read.
- **Tests that need packages** run with the judge's own Python only: `knos referee works` has no setup step.
- **A worker's new tests are not in the judged tree.** The judge copies the base's `tests/` over the delivered
  tree, so a hidden check cannot run the worker's own new test files; run them yourself on the delivered tree.
- **Some cheat rules misfire on honest code.** `hardcoded_answers` fires when new code and its own new tests share
  two string literals, and `references_sealed_bundle` on any code that names `.knos/`. There is no per-task waiver.
