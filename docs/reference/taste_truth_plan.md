# Taste test: the plan, fixed before any prediction

This file is committed, and its sha256 recorded, before either side predicts anything. The test runs once and its
numbers are published in [OUTSIDE_TRUTH.md](OUTSIDE_TRUTH.md) and on How we test Knos, whatever they show.

Data: MovieLens 32M. F. Maxwell Harper and Joseph A. Konstan (2015), "The MovieLens Datasets: History and Context",
ACM Transactions on Interactive Intelligent Systems 5(4). The data is never committed.

Script: [scripts/test_taste_truth.py](../../scripts/test_taste_truth.py). Knos's arm reads GET /api/taste/movie
(apps/wanted/knos_wanted/taste.py), Knos's own Qloo client, which answers names and years only.

## The rules, as written before the run

E4 test_taste_truth (new pre-registered test of what Qloo is built for: taste)
- Question: for people who love a film, which other films do they love? This is the "they also love" line in every Knos result.
- Data: MovieLens 32M from https://files.grouplens.org/datasets/movielens/ml-32m.zip (ratings.csv userId,movieId,rating,timestamp; movies.csv movieId,title,genres; titles end with the year in parentheses). Download into one new empty folder; parse with python -I; never commit the data. Cite F. Maxwell Harper and Joseph A. Konstan (2015), "The MovieLens Datasets: History and Context", wherever results are published.
- Seeds: 30 films chosen with Python random.Random(3).sample from films with at least 20,000 ratings, sorted by movieId first.
- Truth per seed: fans = users who rated the seed 4.5 or more. Candidates = other films with at least 5,000 ratings. For each candidate, lift = (share of fans who rated it 4.5 or more) / (share of all users who rated it 4.5 or more). Keep candidates rated 4.5 or more by at least 300 fans. Truth = top 10 by lift.
- Claude arm: claude -p, web tools denied, prompt exactly: "Reply with exactly 5 lines and nothing else. Each line is one film title and its year in parentheses. The 5 films that people who love <title with year> are most likely to also love, excluding that film." Parse the first 5 non-empty lines.
- Knos arm: through Knos's own Qloo client (the code behind "they also love", harness first, REST fallback as the app does): resolve the seed by Qloo search with type urn:entity:movie, taking the first result whose release year equals the MovieLens year (no match: overlap 0 and log it); then insights with filter.type urn:entity:movie and signal.interests.entities set to that id, take 20; keep the first 5 that map to MovieLens.
- Mapping for both arms: lowercase, strip punctuation and a leading or trailing article (the, a, an), match title plus year exactly; unmapped lines count as misses. Log every unmapped line.
- Metric: overlap at 5 = how many of the 5 are in the truth top 10, divided by 5. Mean over 30. Paired bootstrap, 2,000 resamples, random seed 3, 95% interval for Knos minus Claude.
- Before any prediction: commit a plan file (this section plus the script path) and record its sha256. Run once. Publish on How we test Knos and docs/reference/OUTSIDE_TRUTH.md beside D1, whatever it shows, with the citation. Public files hold only derived titles and scores, never Qloo response bodies.
- Pass: the interval for Knos minus Claude lies above 0. Either way the result is published.

## Choices the rules leave open, fixed here

- A MovieLens title is the text before its final "(year)". When it carries a parenthesised alternate title, such as
  "Amelie (Fabuleux destin d'Amelie Poulain, Le)", both the main title and the alternate are keys. "a.k.a." is dropped.
- Normalising, for both arms and the index alike: accents folded to ASCII (NFKD), lowercase, every character other than
  a letter, a digit or a space removed, one leading or trailing "the", "a" or "an" removed. A key is that text and the year.
- A reply line is read as its text before the first "(year)"; a leading list number or bullet is dropped. A line with
  no year, or matching no MovieLens key, is unmapped and logged; the seed itself never counts.
- Knos searches Qloo with the main title, a trailing article moved to the front ("Matrix, The" becomes "The Matrix").
- Claude alone: claude -p in an empty folder, no MCP servers, WebFetch and WebSearch denied.
- Truth ties in lift are broken by movieId. The rating files are read as sorted by userId, as MovieLens ships them.
