<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Outside truth: open signals against 200 past SBIR awards

**In plain words.** We asked Knos's open-signals check about 200 past research awards whose outcome is known. It did no better than a coin: 47.5% right, where always guessing one side gets 50%. We publish it as measured.

| Measure | Value |
|---|---|
| Awards | 200: 100 commercialized, 100 not |
| Accuracy | 47.5% (base rate 50%) |
| Precision / recall | 47.1% / 40.0% |
| p, binomial vs base rate | 0.78 |
| p, Fisher's exact | 0.57 |

- **Population:** Defense Department SBIR/STTR Phase I awards, 2005 to 2014, with an abstract on sbir.gov.
- **Commercialized:** a granted US patent linked to the award's contract (Zenodo, 10.5281/zenodo.17018422). **Not:** no patent and no Phase II on the same topic.
- **What Knos saw:** one phrase, the award's title or the abstract's first sentence. OPEN counts as a prediction of commercialized.
- **Why it can fail:** open signals measure public attention today, not whether a 2010 defense prototype was patented. A patent is invention, not sales.
- **Since:** the refuse list now applies to demand checks, so ideas naming weapons would be refused, not scored.

Numbers, method and sources: [outside_truth.json](outside_truth.json). Run it again: `python scripts/outside_truth.py <sample.json> --public` (the sample is built from the two public datasets above).

## Kickstarter: 250 held-out projects

**In plain words.** The same question on crowdfunding: did a past Kickstarter project reach its goal? Here 78.8% of the held-out projects succeeded, so always guessing "successful" scores 78.8%. A predictor has to beat that, not 50%. Run 24 Oct 2026, 500 of 500 rows answered.

| Measure, held-out (n=250) | (a) Open signals | (b) Open signals + Qloo |
|---|---|---|
| Accuracy | 64.0% | 59.6% |
| Base rate | 78.8% | 78.8% |
| p, binomial vs base rate | 1.0 | 1.0 |
| p, Fisher's exact | 0.86 | 0.87 |
| Confusion (tp / fp / fn / tn) | 145 / 38 / 52 / 15 | 130 / 34 / 67 / 19 |
| OPEN means (tuned) | failed | failed |

- **Result:** neither predictor beats always guessing "successful". Adding Qloo lowered accuracy by 4.4 points. Like the SBIR result, a demand check is not a forecast of a campaign's outcome.
- **Sample:** 500 successful or failed projects launched 2019 to 2023, from the webrobots.io dump of 2026-10-12, drawn per main category in proportion (seed 0).
- **Split:** 250 tune, 250 held-out, half of each outcome on each side. The tune half picks one thing per predictor: whether OPEN means success or failure.
- **What Knos saw:** the name, the blurb and the category, at most about 200 characters. A refused idea counts as not OPEN.
- **Reading:** the dump is a scrape of Kickstarter's pages, not the full archive. Open signals measure attention today, not a 2021 campaign's backers.

Numbers, method and source: [kickstarter_truth.json](kickstarter_truth.json).

### Tuned on the 250, scored once on the held-out 250

The same rows, now read as numbers instead of one verdict: Wikipedia views and Hacker News stories, the Qloo matches, the
leader's popularity, the top audience affinity, cities and price tier, and each category's success rate in the tune half.

A logistic model was fit on the 250 tune rows only, its cut-off set there too, and the held-out 250 were scored once.

| Measure, held-out (n=250) | (a) Open signals, tuned | (b) Open signals + Qloo, tuned |
|---|---|---|
| Accuracy | 76.8% | 78.0% |
| Base rate | 78.8% | 78.8% |
| p, binomial vs base rate | 0.80 | 0.66 |
| p, Fisher's exact | 0.056 | 0.14 |
| Confusion (tp / fp / fn / tn) | 183 / 44 / 14 / 9 | 190 / 48 / 7 / 5 |

- **Result:** tuning lifts both, and Qloo adds 1.2 points over the open signals, but neither beats always guessing "successful". Past funding outcomes are not what a demand check measures.

Numbers, weights and method: [kickstarter_truth_tuned.json](kickstarter_truth_tuned.json).

Run it again: `python scripts/test_kickstarter_truth.py <ks-sample.json>` (build the sample with `--build` from the dump above).

The tuned one: `--collect <ks-sample.json> <features.json>`, then `--tuned <ks-sample.json> <features.json>`.
