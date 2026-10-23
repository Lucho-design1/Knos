<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# The referee: Works, Wanted, Makeable

**In plain words.** The referee answers three questions about a piece of research or code: does it work, does anyone
want it, and can it be made at a profit. A verdict passes only when all three do.

The person or agent doing the work
cannot see the tests that judge it, cannot change the judge, and is refused when it tries one of the known cheats.
Every verdict and every cheat caught can be written to Knos Record ([RECORD.md](RECORD.md)).

Code: `src/knos/referee/` and `src/knos/cheats/`. Tests: `tests/test_referee_*.py`.

## Works

`referee.works(base, pr, seal, hidden_dir=...)` runs five checks in order; the first that fails decides.

| step | what it checks | refused as |
| --- | --- | --- |
| sealed tests | the hidden bundle's hash is the `spec_hash` sealed before work began (`referee.seal`) | `sealed_tests_changed` |
| locked judge | the hash of the judging code that runs (`knos/judge.py`, `knos/referee/`, `knos/cheats/`) is the sealed `judge_hash` | `judge_drift` |
| cheat rules | the cheat library on the change; no code of the change has run yet | the rule's category |
| hidden tests | `knos.judge.judge` on the hidden bundle, unchanged: fail-to-pass, sentinel and canary, sandbox, the base's tests overlaid | `rejected` or `insufficient_evidence` |
| re-run | the same judgment again, fresh; the verdicts agree, and a number agrees within the sealed tolerance (`abs`, `rel`) | `rerun_mismatch` |

The hidden bundle is kept outside the repository (a private repository or a secret) and is copied into a temporary copy
of the base only for the run, so the worker's tree never holds it. What a worker is shown (`referee.judge_candidate`)
is pass or fail and the rule's name; what the sealed suite printed is withheld.

A second machine is a `judge_fn` that judges there; the re-run on this machine already uses fresh inputs, because a
black-box bundle draws its own.

The referee is never weaker than the judge: the judge's own path rule is the first rule of the library, and the judge
still runs on everything the rules let through.

## The cheat library

`cheats.scan(base, pr)` (two trees) and `cheats.scan_diff(diff, base_dir=...)` (a `git diff`) run every change rule;
`cheats.scan_outcome(funded, now)` runs the outcome rules. `knos cheats list` prints each rule; `knos cheats red-team`
runs every known case. A new cheat type becomes a rule with `cheats.add_rule` together with its known-bad case and a
test; ids are never reused and rules are never removed.

The first 63 entries are the tamper benchmark's attacks on the slugify sample, 21 in each of Python, JavaScript and
Ruby ([TAMPER.md](TAMPER.md)). Each names the rule that refuses it, and `tests/test_referee_cheats.py` builds every one
and checks that rule fires before any code runs.

The cases that no text rule could see in principle (a no-op claim, constants for the visible examples, forgery from
inside the test process) are also judged with the rules switched off, and the sealed black-box tests refuse each of
them on their own.

The 63 cases by the category of the rule that refuses them:

| category | cases |
| --- | --- |
| spec_tampering | 21 |
| runner_forgery | 18 |
| runner_tampering | 10 |
| test_edited | 5 |
| hardcoded_answers | 3 |
| no_change | 3 |
| workflow_edited | 3 |

The rules on a change:

| rule | category | what it catches |
| --- | --- | --- |
| spec_file_edited, workflow_edited, test_edited, test_deleted, unrestored_test_config | spec_tampering, workflow_edited, test_edited, runner_tampering | the judge's own path rule (`knos.judge.classify_path`), word for word |
| detects_test_runner | runner_forgery | code that checks whether a test runner loaded it |
| references_sealed_bundle | runner_forgery | code that names the acceptance bundle's folder |
| runner_patch | runner_forgery | code that patches pytest, minitest or node:test |
| assert_disarmed | runner_forgery | code that makes assertions stop failing |
| exit_in_test_process | runner_forgery | a file the runner loads ends the process |
| forged_test_report | runner_forgery | a test report added to the tree |
| skip_added, trivial_assertion | test_edited | tests skipped, deferred or asserting nothing |
| runner_options_tampered, test_script_changed | runner_tampering | options or scripts that change which tests run |
| hardcoded_answers | hardcoded_answers | an input and its expected answer from the same visible test line, written into the code |
| no_source_change | no_change | documentation only, for a claim that the work is done |
| out_of_scope | out_of_scope | a file outside the paths the issue allows (a new test beside the protected ones is allowed) |
| core_path_touched | core_path | a trusted-core path (the self loop's referee, programs, workflows) |
| assertion_removed, detector_marker_removed | assertion_removed | assertions or `knos:detector` markers removed from an existing test |

The outcome rules: `outcome_spec_hash_changed`, `outcome_window_changed`,
`outcome_salt_changed`, `outcome_control_drift` (beyond the agreed tolerance), `outcome_measurement_code_drift` and
`outcome_data_tampered` (data that existed at funding edited or removed; new data is not refused).

How the rules read a change. The repository's language (which directories hold its tests) comes from the base tree
and its `.knos/proof.toml`, never from the files the change adds.

A `git diff` is read with git's quoted paths (non-ASCII names, spaces) and with files that have no `diff --git` line;
a `package.json` edit in a diff counts as a test-script change only when an added or removed line names a test
script.

A rule that crashes, or a diff header that cannot be read, is a refusing `rule_error` finding: the library fails
closed, never open.

Changed in v0.3.31: two rules refused honest work, and both were narrowed. Per [SELF.md](SELF.md), `cheats/` is trusted
core, so a referee change waits for the signature on the release. What changed:

- `hardcoded_answers` counts a visible test line only when the test holding that line exercises the changed file.
  "Exercises" means the test imports the file (Python by module name; JavaScript and Ruby by the file's name in a
  `require`/`import` path; the runner's helpers such as `conftest.py` or `test_helper.rb` count for every test), names
  the file in a string ("calc.py"), or runs it with `-m`. It also covers another changed file that such a file
  imports, so moving the answers into a new module that the tested code imports is still refused. Field names
  (`x["amount"]`, `.get("key")`, dict keys) are left out of a test line's literals because they describe the
  protocol's shape, not an input or an answer. A test with no import line, Go and Rust tests, and a `.json` fixture
  with no test reading it by name keep the strict 0.3.30 reading.
- `references_sealed_bundle` passes a literal that names a specific other file under `.knos/` (`.knos/gate.yml`,
  `.knos/proof.toml`). It still refuses the folder itself (`".knos"`, `".knos/"`), anything under `.knos/acceptance`,
  dynamic or relative names (`f".knos/{x}"`, `.knos/../`), and a line it cannot read.
- `red_team()` still catches 63 of 63. Without `hardcoded_answers` the count drops to 60, as before.
  `tests/test_referee_cheatfp.py` holds the known-good cases and the known-bad ones that are still refused.

Limits that remain: a test that reaches code only through a hub module (a CLI that imports every command) still counts
as exercising whatever that hub imports. A write guard that names the whole `.knos/` folder reads, as text, the same
as the forgery, so it is still refused.

Measured on three 0.3.31 patches (scanned as diffs against a4ea15cf), these two
rules refused 22 files before the change and 12 after: hardcoded_answers went from 20 to 11 and
references_sealed_bundle from 2 to 1.

What is not stopped: the rules read text, so a cheat written in a way no rule names can pass them. That is why the
sealed black-box tests run after them; the benchmark measures how the two walls do together, and the honest
submissions of the benchmark are checked against the rules too (none is refused).

## Wanted

`referee.DemandBook().lock(spec_hash, buyer, amount, escrow_ref=...)` records a pre-order;
`referee.wanted(orders, min_buyers=N, min_locked=X)` passes when N distinct buyers have X locked. Only orders with an
held-money reference count (a pledge is shown and not counted), each buyer counts once, and the bar is set by whoever asks.
Amounts are integers in the currency's smallest unit.

## Makeable

`referee.makeable(quotes, locked_price=P, min_margin=m, fees=f)` passes when the quotes' cost plus fees is at most
`P * (1 - m)`. Every quote must name its source; an expired quote, a missing required kind or mixed currencies refuse.
Fees come from the one fee config (MONEY), passed in.

## The verdict

`referee.verdict(works, wanted, makeable, spec_hash=...)` passes only when all three pass, and writes one `verdict`
entry and one `cheat` entry per cheat caught to Knos Record when the install has it.

`referee.reward(check)` gives an evolving agent 1 for work that passed, 0 for work that failed, and -1 for work a
cheat rule refused, so cheating is never better than failing (the referee as a judge for skill evolution and training
environments).

## Free maintainer mode

The free Knos check (`action.yml`) gains `maintainer-mode`: `off` (the default), `comment`, `label` or `close`.

With it on, the check reads the pull request's diff with the cheat library and labels a pull request that edits
existing tests, touches files outside `scope`, or fails the check; `close` also closes it with one comment naming the
rule and asking for a new pull request.

Knos's own labels whose cause a later push removed are taken off again. The `scope` globs reach Knos as written (the
shell never expands them). No money, no wallet and no chain are involved, and none of the pull request's code runs.

Install: add the Knos check workflow from [INSTALL.md](INSTALL.md), give the job `pull-requests: write` and
`issues: write`, and add `with: maintainer-mode: label` (or `close`) to the `uses: drexthealpha/Knos@...` step; add
`scope: "src/** docs/**"` to name the paths outside contributors may touch.

The decision is made by `knos referee maintainer --base DIR --diff FILE --mode MODE`; the action applies it with
the job's own token.
