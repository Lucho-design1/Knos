# Task packages: a merged fix as a sealed, verified task

**In plain words.** When a maintainer merges a pull request that fixes an issue and adds tests, that pair is a good
task: a real problem, a real fix, and tests that tell right from wrong. `knos taskpack export` packs it. The tests are
sealed, so a solver cannot see them.

Knos checks that the tests fail before the fix and pass after it. Anyone holding
the package can then grade a new attempt, and attempts that edit the tests or wander outside the fix's files are refused.

Only the maintainer opts a task in. Selling task packages is a founder decision; nothing here offers or sells one.

## Why

AI labs buy software tasks to train and test agents. Epoch AI reported prices of $200 to $2,000 per task, and that
resistance to reward hacking is the first thing buyers ask for (Epoch AI, 12 Jan 2026).

A task whose hidden tests come from the fix that was actually merged, with cheat rules applied before any test runs,
is that kind of task.

## Export

```
knos taskpack export owner/repo#PR --repo-dir CLONE [--opt-in --maintainer LOGIN] [--encrypt] [--price MICRO_USDC]
```

- Reads the pull request and the issue it closes from GitHub (or offline: `--merge SHA --issue N --issue-title ...`).
- **Opt-in**: `.knos/taskpack.yml` with `export: true` at the merge commit, or `--opt-in` from the maintainer running it.
  Without either, nothing is exported.
- Splits the fix into test files (sealed) and the rest (the reference fix, sealed too).
- Runs the tests at the base commit (they must FAIL) and at the merge (they must PASS), each in a copy unpacked with
  `git archive`. The clone is only read.
- Reads the licence (`LICENSE` / `COPYING`). No licence: the package is for the copyright holder's own use and is marked
  not sellable.
- Fee: the split of a sale comes from the one fee config, `config/fees.yaml`, through `knos.money.fees_config`
  (`task_package`). Prices are a founder decision, so without `--price` only the source is recorded.

```
<task_id>/public/task.json        manifest: source, licence, opt-in, statement, scope, judge, sealed hashes, the check, fee
<task_id>/public/statement.md     what the solver reads
<task_id>/sealed/tests.tar        the hidden tests (with --encrypt: tests.tar.enc, ChaCha20-Poly1305, key written beside the package as `<task_id>.key`, never inside it)
<task_id>/sealed/reference.patch  the merged fix without its tests
```

The task id comes from the spec hash: sha256 of the manifest, which commits to the sealed files' hashes.
`knos taskpack verify PACK` recomputes both. Nothing in `public/` shows a hidden test's name or content.

## Grade

```
knos taskpack grade PACK --patch candidate.patch --repo-dir CLONE
```

Cheat rules first, and no candidate code runs when one fires: `test_edited`, `out_of_scope` (outside the folders the
fix touched), `workflow_edited` (`.github/`, `.knos/`), `no_change`. When the referee's cheat library is installed
(`knos.cheats.scan_diff`) its findings count too. Then the hidden tests run at the base commit with the patch applied.
The output names counts and rules, never a hidden test.

Reward on the referee's scale: 1.0 pass, 0.0 fail, -1.0 cheat.

## For training environments and the referee

`knos taskpack rows PACK... --out tasks.jsonl` writes one row per package: the statement, repository, base commit,
scope and sealed hashes. `knos.taskpack.atropos.score(row, clone, patch)` returns the reward, for a Hermes Atropos
environment. `knos.taskpack.atropos.referee_spec(pack)` gives the referee the spec hash, hidden-test hash, judge and
rules. Devnet and demo use only.

## Shown on the owner's own repository

On 13 Oct 2026, on a read-only clone of `drexthealpha/knos-e2e`, pull request #272 (closes #271):

- without opt-in: refused;
- with `--opt-in --maintainer drexthealpha`: package `knos-task-9f777dfb79758fdd`, 1 hidden test file, failing before
  the fix and passing after it; no licence file, so marked not sellable;
- grading: the merged fix 1.0, a patch that rewrites the test -1.0 (`test_edited`), a wrong fix 0.0.

The manifest, the three candidate patches, their grading output, the training row and `run.sh` are in
[evidence/repro-0329/](evidence/repro-0329/run.sh). Grading runs the candidate's code on the grading machine without a
sandbox: grade untrusted patches inside a disposable container or VM. A training row holds no path to the package.

Source: `src/knos/taskpack/`, tests `tests/test_taskpack_*.py`.
