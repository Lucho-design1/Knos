# Qloo API: what this app calls, and where each detail is documented

Every endpoint, parameter and response field the app uses was checked against Qloo's official documentation at
docs.qloo.com on 14 Oct 2026. "Updated" is the page's own last-updated stamp at that time. Nothing here is Qloo
response data.

| What the app uses | Qloo page (updated) |
|---|---|
| Base URL `https://hackathon.api.qloo.com`; header `X-Api-Key`; hackathon keys fail (401) on staging and production URLs; `/recommendations` and `/recs` not supported; a 403 means the entity type is not available; private server-side caching allowed, never response data in a public repository | [Qloo Agentic Hackathon Developer Guide](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide) (2026-10-07) |
| `GET /search` with `query`, `types`, `take`; response `results[]` of entities | [Search Entities](https://docs.qloo.com/reference/get-search) (2026-07-20) |
| `GET /v2/tags` with `filter.query`, `take`; response `results.tags[]` | [Search Tags](https://docs.qloo.com/reference/search-tags) (2026-07-08) |
| Tag object fields `tag_id`, `name`, `types`, `subtype` | [Taste Analysis](https://docs.qloo.com/reference/taste-analysis) (2025-11-12) |
| `GET /v2/insights` with `filter.type` (required), `signal.interests.entities`, `signal.interests.tags`, `signal.demographics.age` (values such as `24_and_younger`, `25_to_29`, `30_to_34`, `35_to_44`, `45_to_54`, `55_and_older`), `signal.demographics.gender` (`male`, `female`), `filter.results.entities` ("often used to assess the affinity of an entity towards input"), `take` (max 50); response `results.entities[]` | [Insights API Deep Dive](https://docs.qloo.com/reference/insights-api-deep-dive) (2026-07-08) |
| `feature.explainability=true`: per result `query.explainability` (input contributions, normalised 0 to 1); top-level `query.explainability` (average influence over top-N subsets); `query.explainability.warning` when it cannot be computed | same page (2026-07-08) |
| Entity fields `name`, `entity_id`, `subtype`, `popularity`, `tags[]`, `query.measurements.audience_growth` | [Recommendation Insights](https://docs.qloo.com/reference/basic-insights-use-case) (2025-10-27) |
| `filter.type=urn:demographics` with `signal.interests.entities` or `.tags`; response `results.demographics[].query.age.*` and `.gender.*`, positive = stronger than average | [Demographic Insights](https://docs.qloo.com/reference/demographics-use-case) (2025-10-27) |
| `filter.type=urn:heatmap` with `filter.location.query`; response `results.heatmap[]` with `location.latitude/longitude/geohash` and `query.affinity/affinity_rank/popularity` | [Heatmap Insights](https://docs.qloo.com/reference/heatmaps-use-case) (2026-07-08) |
| `filter.location.query`: fuzzy locality name | [Parameter Reference](https://docs.qloo.com/reference/parameters) (2026-07-08) |
| `GET /v2/trending` with `filter.type`, `signal.interests.entities`, `filter.start_date`, `filter.end_date` (YYYY-MM-DD); response `results.trending[]` with `date`, `population_percentile`, `population_rank`, `population_rank_velocity`, `velocity_fold_change`, `population_percent_delta` | [Get Trending Data](https://docs.qloo.com/reference/get-trending) (2026-07-08) |
| `GET /v2/analysis/compare` with `a.signal.interests.entities`, `b.signal.interests.entities`, `take`; response `results[]` of entity objects; 404 "no results", 429 rate limit | [Analysis Compare](https://docs.qloo.com/reference/analysis-compare) (2026-07-08) |

## Where the docs leave a gap, and what the app does

- The per-result `query.explainability` object's exact layout is described in words, without a JSON example. The
  app reads any list or mapping of input ids to scores (`report.drivers`); the mock uses a list per signal.
- The items of `/v2/analysis/compare` are documented only as entity objects; the app shows their names in order and
  claims nothing more about them.
- The hackathon guide lists `urn:entity:video_game` and `urn:entity:destination`; the Insights reference lists
  `urn:entity:videogame` and `urn:entity:locality`. The probe tests both spellings and records the status codes.
- `urn:demographics` and `urn:heatmap` are documented in their use-case pages; whether the hackathon key serves
  them is exactly what `python -m knos_wanted probe` records.
