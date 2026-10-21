# Knos (Devpost text)

**Tagline:** An agent that carries research across the valley of death: Qloo decides who wants it, where, at what price, and whether pre-orders open.

**Try it:** https://knos.onrender.com (no sign-up to check demand) · front door: https://drexthealpha.github.io/Knos/#demand
**Code:** https://github.com/drexthealpha/Knos (MIT) · **Status:** Solana devnet, test money, no customers yet.

## Inspiration

Most research that works never becomes a product. A paper proves a result, then stalls: nobody can say who would buy
it, where, or at what price, so nobody funds the next step. We wanted an agent that takes a paper or an idea and
answers the demand question first, with real taste data, before anyone puts money in.

## What it does

Paste a DOI or arXiv id, or describe an idea. The Knos crossing agent reads the paper, names the product, and asks
Qloo who wants it, where to launch it and at what price tier. Published rules (no language model) turn Qloo's
evidence into a verdict: OPEN for pre-orders, or REFUSE with the reason. An open product gets a Ready brief, whose
milestones each have a number to hit, who checks it and a deadline. Backers fund milestones into escrow on Solana,
and the maker is paid only on verified proof; without proof by the deadline the money goes back.

Every Qloo-derived value on the page links to the exact request behind it (endpoint, parameters, entity and tag
ids, no key), an excerpt of the result, and its limit: aggregate taste, not causal, not about a person.

## How Qloo is used

- `/search`, `/v2/tags`: the closest existing products and the idea's taste tags, kept only when they share the idea's words.
- `/v2/insights` with `urn:demographics`, `urn:audience`, `urn:entity:destination`, `urn:entity:place`, `urn:heatmap`: who, segments, launch cities, places and price levels.
- `/v2/analysis/compare`, `/v2/trending`: room beside the market leader and its trend.
- `@qloo/qloo-harness` (`qloo mcp`): the crossing agent's own `qloo_*` tools.
- Seven families of options (who, gaps, where, price tier, who serves it, media kind, look-up) are the same controls in
  the app, typed arguments of the hosted MCP server, API fields and CLI flags.

Measured: 20 ideas from 10 fields, each with Qloo and with the key unset. With the key unset Knos cannot decide; with
Qloo it decided all 20 and set the audience, cities and price tier in 9 (https://knos.onrender.com/with-without).

## How we built it

Python on the server (standard library HTTP, Qloo's REST API and MCP harness), plain JavaScript pages, Solana devnet
programs for escrow, and the SPL Record program to keep projects across redeploys. The demand check asks Qloo's
independent questions at once, so a first verdict usually comes back in under 10 seconds.

## Safe use

Knos sends no personal data to Qloo, refuses any ask to infer a person's health, finances, politics or identity, says
plainly when Qloo refuses the key or rate-limits, and keeps retries bounded. Every rule of the kit's SAFE_USE and
API_ACCESS documents is mapped to its code and test: https://knos.onrender.com/qloo-safe-use

## Challenges

Qloo knows a lot about consumer taste and little about some new technical spaces; Knos shows that instead of
guessing. Keeping every number tied to its source, on phone and desktop, took more work than computing it.

## What is next

People outside Knos crossing their own research: the live count is at https://knos.onrender.com/invite.

## Built during the hackathon

Knos existed before 30 September; the Qloo demand layer, the traces, the with-and-without measurement, the safe-use
mapping, persistent projects and the outside counter were built during the Submission Period. Every commit since
then is listed by day in docs/submission/UPDATES.md.
