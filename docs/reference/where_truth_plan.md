# Where-demand test: the plan, fixed before any prediction

This file is committed, and its sha256 recorded, before either arm predicts anything. The test runs once and its
numbers are published in [OUTSIDE_TRUTH.md](OUTSIDE_TRUTH.md) and on How we test Knos, whatever they show.

Script: [scripts/test_where_truth.py](../../scripts/test_where_truth.py)

## The rules, as written before the run

D1 test_where_truth (replaces C1; no API key, no account)
- Truth file: https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23msa.zip (County Business Patterns 2023, metro areas, all NAICS levels). Layout: https://www2.census.gov/programs-surveys/cbp/technical-documentation/records-layouts/2018_record_layouts/metro-area-layout-2018.txt . Read the layout to find the area-code, NAICS and establishment-count columns; log the names you used.
- Population file: https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/metro/totals/cbsa-est2023-alldata.csv . Columns CBSA, LSAD, POPESTIMATE2023. Keep rows whose LSAD is "Metropolitan Statistical Area".
- Download both into one new empty folder; parse with python -I; never run anything from inside the zip.
- Candidate metros: Metropolitan Statistical Areas with POPESTIMATE2023 of at least 500,000. Both predictors choose only from these.
- The 30 NAICS codes, the business-type phrase (official NAICS title), the claude -p prompt, the CBSA name matching, the Knos heatmap-to-CBSA method (TIGER/Line 2023 boundaries already shipped in commit c769b83), the overlap-at-5 metric and the 2,000-resample paired bootstrap are exactly as in TASK-CHAMPION-spec section C1.
- Truth per code: rate = establishments / POPESTIMATE2023 x 100,000; top 10. If a code has no row in cbp23msa, log it and drop that code from both arms (report n).
- Before any prediction: commit the plan file (this section, the C1 section it points to, the script path) and record its sha256.
- Knos arm uses the D2 launch-city method only for ranking (mean affinity per CBSA, CBSAs with at least 3 heatmap cells; if fewer than 5 such CBSAs, fill with CBSAs with 1-2 cells by mean affinity). An idea with no heatmap cells counts as overlap 0 for Knos.
- Run once. Publish the exact numbers (mean overlap each arm, difference, 95% interval, n, the plan sha256, the claude model and version) on the How we test Knos page and in docs/reference/OUTSIDE_TRUTH.md, whatever they show. No Qloo response bodies in public files: only the derived top-5 CBSA codes.

### The base rules it points to

C1 test_where_truth
- Business types, exactly these 30 NAICS codes: 713940, 312120, 722515, 722511, 722513, 722410, 812111, 812112, 812113, 812910, 541940, 713110, 713120, 713910, 713950, 711130, 711110, 512131, 611610, 611620, 621310, 812199, 811192, 721110, 721191, 312130, 312140, 311811, 624410, 712110. Use each code's official NAICS title as the business-type phrase.
- Candidate metros: Metropolitan Statistical Areas with population of at least 500,000 in the ACS 1-year estimate for the same year as the CBP data. Both predictors choose only from these.
- Truth: Census County Business Patterns API, latest published year, geography metropolitan statistical area, field ESTAB for the code; rate = ESTAB / population x 100,000; top 10 per code. If a code is absent in that year's NAICS vintage, use the Census concordance equivalent and log the mapping.
- (a) Claude alone: claude -p with exactly: "From US metropolitan areas with at least 500,000 people, list the 5 where <NAICS title> businesses are most common per person. Reply with 5 metro area names, one per line, nothing else." Map names to CBSA codes by exact or fuzzy match against the candidate list; log the model name and version.
- (b) Knos: run the business-type phrase through Knos's normal demand-check path; take the Qloo heatmap cells, assign each to a CBSA using TIGER/Line 2023 CBSA boundaries, rank CBSAs in the candidate list by mean affinity, take the top 5.
- Metric: overlap at 5 = how many of the 5 are in the truth top 10, divided by 5. Mean over 30. Paired bootstrap, 2,000 resamples, 95% interval for (b) minus (a).
- Commit the plan file (this section copied plus the script path) and record its sha256 BEFORE any prediction is made. Run once. Publish the exact numbers on the How we test Knos page and docs/reference/OUTSIDE_TRUTH.md, whatever they show.

## Choices the rules leave open, fixed here

- Business-type phrase: the official title in the Census CBP reference file naics2017.txt, the newest NAICS
  descriptions file the CBP reference publishes; all 30 codes have rows in cbp23msa (n = 30).
- Candidates: 110 Metropolitan Statistical Areas with POPESTIMATE2023 of at least 500,000; all have CBP rows.
- Columns used: cbp23msa msa, naics, est; cbsa-est2023-alldata CBSA, LSAD, POPESTIMATE2023, NAME.
- Truth ties in the rate are broken by CBSA code.
- Claude alone: claude -p in an empty folder, with no MCP servers (--strict-mcp-config); the first 5 non-empty reply
  lines. A line matches a candidate by exact name, else by the best difflib ratio over the full name and over its first
  principal city with state, when the ratio is at least 0.6; an unmatched line counts as a miss.
- Knos: the demand check's heatmap metros (all metros holding cells) restricted to the candidates; ties by cell count,
  then CBSA code.
- Bootstrap: Python random.Random(1), 2,000 paired resamples of the codes, percentile interval (2.5% and 97.5%).
