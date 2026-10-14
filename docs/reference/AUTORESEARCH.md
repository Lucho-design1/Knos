# Autoresearch for anyone

**In plain words.** You write what you want in plain English and give a starting idea. Agents (any: Claude Code,
Codex, Hermes, or a built-in deterministic one) change one file and run it for a fixed time. Only the Knos referee
decides whether a change is kept, by scoring it on data the agent never sees. Before anyone is paid, the best version
must beat the starting point again on a second hidden set that no experiment ever touched.

The loop is the autoresearch pattern Andrej Karpathy published (an agent edits one file, each run has a fixed time
budget, keep the change if it is better). The example below is small, runs on a CPU in about a minute, and all of its
data is **synthetic**.

## Run it

    PYTHONPATH=src python -m knos.autoresearch run examples/autoresearch --out /tmp/ar --iterations 12

No key, no network: the default proposer is deterministic. To let a coding agent propose instead, give its command;
the prompt goes to its stdin and it prints the whole new file (its own login or key; Knos neither reads nor stores it):

    --proposer "cmd:claude -p"        --proposer "cmd:codex exec -"        --proposer "cmd:<any command>"

Outputs: `results.tsv` (one row per experiment), `best_train.py`, `summary.json`, and the record under `record/`.
The command exits 0 when the result graduated, 1 when it did not, 2 when the task folder is invalid.

## The researcher's folder

| file | what it is |
|---|---|
| `program.md` | what you want, in plain English; agents read it, nothing parses it |
| `idea.md` | the starting idea |
| `task.json` | the terms: the one editable file, metric and direction, time budget per run, keep bar (`keep_delta`), re-run tolerance, graduation bar (`min_lift`), two seeds, the data, the sealed file's sha256, the bounty and shares |
| `train.py` | the one file agents may change; the baseline |
| sealed file | what only the referee holds: here a seed from which the hidden sets are generated |

## What the referee does (`knos.autoresearch.judge`)

1. **Seal first.** The spec hash covers program.md, idea.md, task.json, the baseline, the sealed file's hash and the
   hash of the judging code itself. It is the first thing written to the record. A sealed file whose hash differs
   from the one task.json committed to is refused.
2. **Static rules, before any candidate code runs** (each a named rule; the category is Knos Record's `cheat` field):
   `AR-SCOPE` out_of_scope (any file but the editable one), `AR-NOCHANGE` no_change, `AR-IMPORT` runner_tampering (an
   import outside argparse, bisect, collections, csv, functools, heapq, itertools, json, math, random, statistics,
   time; `__import__`, `eval`, `exec`, `compile`, `getattr`, `setattr`, `importlib`, `open` of a literal path; any private
   attribute such as `random._os`, any dunder name but `__name__`, or an attribute that leads to the operating system such
   as `statistics.sys.modules`), `AR-SEALED`
   data_tampering (a string naming "sealed", "hidden", "..", or an absolute path; docstrings excepted). When the
   shared cheat library `knos.cheats` is installed, its `scan(base, pr, scope=[editable])` runs too.
3. **Two runs** in a fresh directory holding only the candidate, the public data and the hidden rows' features
   (never their labels), Python's isolated mode, an almost empty environment and a hard wall-clock limit. Score =
   mean accuracy of the two seeds on the hidden dev set. `AR-RERUN` rerun_mismatch refuses when the two differ by
   more than the tolerance. A crash or a run over budget fails the candidate without calling it a cheat.
4. **Keep if better.** Kept only when it passes and beats the current best by more than `keep_delta`. The agent is
   told its change, its own validation score, the decision and the reasons: never a hidden score.
5. **Graduate on data nobody saw.** Baseline and best are scored on `hidden_final`, used nowhere else, with both
   seeds. Graduation needs the lift on each seed to be at least `min_lift`, both re-runs to agree, and the judging
   code to hash as it did when the spec was sealed (else `judge_drift`).

**Limit: this is a static filter and a process boundary, not an OS sandbox.** The candidate runs as the referee's own
user. The rules above close the bypasses found in review (`sys.modules["o"+"s"]`, a module's private `_os`), but a
determined candidate may still find a path they miss and read any file that user can read, such as this demo's sealed
seed. The hidden labels are never on disk in the sandbox. Before real money depends on it, the referee must run
candidates on a machine or account that holds neither the sealed file nor the hidden labels.

## The record and the payout

Every step goes to Knos Record through `knos.record` (`claim`, `paper`, `append`) when it is installed: the research
claim as a Sibyl WARM entity, program.md and idea.md by hash as a REFERENCE, and each experiment, cheat, refusal,
verdict, graduation and split plan as a COLD event in one hash-chained journal. Payloads are hashes, scores,
decisions and amounts; never source code. On an install without `knos.record` the same entry shape is kept in
`record/autoresearch-journal.jsonl` and Sibyl (`record/sibyl.db`). `--anchor` asks `knos.record` to anchor the
journal's Merkle root on devnet (`--anchor-keypair FILE` names the payer); it is off by default, and a failed anchor
is reported in summary.json instead of stopping the run. Text from an agent or a candidate (a change's description,
a crash's last line) goes in only when it is short plain words; anything else is replaced by its sha256. The
fallback journal's Merkle root is computed as `knos.record.merkle` computes it.

After graduation the run writes an outcome (metric, baseline, best, lift per seed, the bar, the spec hash) and a
**split plan**: the whole bounty in task.json, divided by the role shares of the one fee config (`knos.money.fees_config`,
config/fees.yaml; only roles the config has) when it is installed, else by task.json's shares. The payout fee is the
funder's, on top of the bounty, as fees.yaml says; the agents' part is
divided among the agents whose changes were kept. It is a plan: nothing is signed or sent. Paying it is graduation's
job (an escrow order on devnet).

## A measured run (synthetic data)

Measured on 13 Oct 2026 in the build machine's WSL VM (4 CPUs, 4 GB), 12 experiments, default proposer, seed 0.
All numbers are accuracies on synthetic data generated by `knos.autoresearch.synth`; reproduce them with the command
above.

| | baseline | best |
|---|---|---|
| hidden dev set (400 rows, mean of 2 seeds) | 0.4875 | 0.94125 |
| hidden final set (1,000 rows, never used in the loop), seed 1 / seed 2 | 0.500 / 0.497 | 0.928 / 0.930 |

Experiments: 12; kept 7, discarded 5, refused 0, failed 0. Lift on the final set: 0.4305 (bar 0.05): graduated.
Wall time for the whole run: 47.5 s. The record held 19 entries and verified. The kept changes, in order: squared
features, pairwise products, batch 16, learning rate 0.1, 20 epochs, learning rate 0.2, L2 0.001.

The same command run again while other jobs loaded the VM (load average 9.8 on 4 CPUs) took 115.6 s: experiment 11
(40 epochs) ran past the 20-second budget and failed, so 4 were discarded and 1 failed; every other decision and every
score above came out the same. The budget is wall-clock time, as in the original pattern, so a busy machine can fail
a run that a quiet one passes; a hosted referee runs on a machine of its own.

The split plan, from a re-run in the merged v0.3.29 tree (same scores; 106.9 s at load average 10.9) with its fee
config (the shares were placeholders then; the founder decided the same 60/25/10/5 on 14 Oct 2026, config/fees.yaml): bounty 100 test USDC
(a demo amount) split researcher 66.68, agent 27.77, referee 5.55; the payout fee 0.30 is the funder's, on top, so the
funder pays 100.30 on chain (the 5% bounty fee decided on 14 Oct 2026 includes that 0.30; its off-chain rest is not
part of this plan: see MONEY.md). No transaction.

## What is not done here

- The hidden sets' seed is in the repository, so anyone can reproduce the run; it also means it is not hidden from
  anyone who reads the repository. A real referee keeps the sealed file off the agent's machine.
- Wanted and Makeable (the demand book and the cost check of the referee's full verdict) are not assessed in this
  example; the verdict here is Works only.
- The run anchors nothing and pays nothing by default.
