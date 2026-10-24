# Plan: does Qloo rank Kickstarter funding better? (fixed before the run)

This file is committed before any of the projects below is checked. Its sha256 is printed with the result, so
anyone can see the rules did not move after the numbers came in.

## Sample

- Source: the webrobots.io Kickstarter dump of 2026-10-12 (`Kickstarter_2026-10-12T07_08_07_724Z.json.gz`,
  sha256 e27490898e74ed929e02dffba21a98c067d83a5cf953aca4ebd556852b99b80b), one record per project id.
- Eligible: state successful or failed, launched 2019-01-01 to 2023-12-31 (UTC), goal above 0, a blurb, and
  not one of the 500 projects of the earlier test (docs/reference/kickstarter_truth.json).
- Drawn: 300 projects, `random.Random(1).sample` over the eligible projects sorted by numeric id.
- Knos reads the same line as before: `name: blurb`, cut to 200 characters, then `(main/sub category)`.

## Scores

Two scores per project, from the two models of the earlier tuned test (docs/reference/kickstarter_truth_tuned.json),
fit again by the same code on the same 250 tune rows. The fit is deterministic, and it is fixed before any new
project is read.

- (a) open signals: the model's probability from the open-signals features and the category's tune-half rate.
- (b) open signals + Qloo: the same with the demand check's Qloo features added.

## Outcome and analysis

- Outcome: pledged divided by goal, both in the project's own currency.
- Measure: Spearman's rank correlation between each score and the outcome over the 300 projects (ties take their
  average rank).
- The question: rho(b) minus rho(a). A 95% interval from 2,000 bootstrap resamples of the 300 projects, paired (the
  same resample for both scores), drawn with `random.Random(1)`, percentile method.
- Qloo helps if the interval lies above 0, hurts if below, and the test cannot tell if it holds 0.
- Run once. The result is published in docs/reference/OUTSIDE_TRUTH.md whatever it shows.
