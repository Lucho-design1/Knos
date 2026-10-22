# Labs: the physical step of the flow, paid on two verdicts

**In plain words.** Research dies between a good design and a real thing. Knos is the layer that says what machine
and lab work is real and pays for it, so ideas from anyone, in every field, can cross that valley toward the machine
economy Schmidhuber describes (arXiv 2212.11279, Sec. 20). This page is step 5 of that flow: the best designs go to
cloud labs and fabs through **one** interface. The lab is paid when it did the work right. The researcher is paid when
the science held.

Everything below runs on Solana devnet with test money. Lab replies come from labelled fixtures. No real order was
placed, no real money moved, and no lab account was opened.

## One interface for every lab (`src/knos/labs/`)

```text
quote(spec)            -> price, currency, turnaround
order(spec, escrow)    -> the lab's order id, bound to the Knos escrow that pays it
status(order)          -> draft | quoted | submitted | in_progress | qc | completed | failed | cancelled
results(order)         -> runs (failed runs included, each with why), QC, raw file hashes
```

Each adapter runs in **fixture** mode (recorded or documented responses, used by every test) or **live** mode. Live
mode uses *your own* key for that lab, read from one environment variable and never printed or recorded (bring your
own key). Knos never resells a lab's service. A live call that spends money also needs `KNOS_LABS_LIVE_ORDERS=1`.

| Field | Adapter | State | Key (env) | Read from |
|---|---|---|---|---|
| proteins | `adaptyv` | live-ready (BYOK); fixtures in CI | `ADAPTYV_API_KEY` | docs.adaptyvbio.com/llms-full.txt; devs.adaptyvbio.com/api/v1/openapi.json (v0.0.2) |
| chemistry | `b12_selenium` (retrosynthesis routes) | live-ready (BYOK) once b12 gives you its base URL (`KNOS_B12_SELENIUM_BASE`) | `B12_API_KEY` | b12-labs.com/docs/selenium-route-search/openapi.json (v0.1.0) |
| chemistry | `b12_foundry` (synthesis) | manual lab: ordered by e-mail, no API | none | b12-labs.com/foundry |
| materials | `materials_project` (computed ground truth) | live-ready; a key is required | `MP_API_KEY` | api.materialsproject.org/openapi.json; docs.materialsproject.org |
| electronics | `pcbway` (fabrication) + a sealed bench test | live-ready with a partner key | `PCBWAY_API_KEY` | api-partner.pcbway.com/Help and its partner PDF |
| electronics | `jlcpcb` | stub (access by application) | `JLCPCB_APP_KEY` | api.jlcpcb.com |
| mechanical | `xometry` | stub: its API is for manufacturing partners, not buyers | none | developer.xometry.com/llms.txt |
| robotics | `pylabrobot` (simulation as sealed tests, re-runs) | runs locally, no key | none | docs.pylabrobot.org; PyPI `pylabrobot` |
| any | `manual` | Knos holds the escrow; a person orders and brings the files back | none | |

These are examples, not the plan: any lab plugs in as one more adapter.

The plain contract over them (`knos.labs.ADAPTERS`, `settle`, `public_view`, `knos.leitner.step`) takes and returns
dicts. Each adapter carries an `example` spec its fixtures answer, and `order(spec, None)` raises: there is no order
without money in escrow. A free service (computed data, simulation) is quoted at the Knos check price, and the quote
says so in `price_basis`.

What each lab's docs say that shaped its adapter:

- **Adaptyv.** A bearer token comes from the Foundry portal (Organization, Settings, Tokens). The cost estimate is
  `POST /experiments/cost-estimate`, priced in USD cents. The order is `POST /experiments` with
  `payment.method = "x402-exact"`. Accepting the quote (`/quote/confirm`) "never moves money". The invoice is paid at
  `POST /invoices/{id}/pay`: a 402 carries the challenge in the `PAYMENT-REQUIRED` header, and the answer goes in
  `PAYMENT-SIGNATURE`, as x402 v2 `exact` with EIP-3009 USDC on Base. Results come from `GET /experiments/{id}/results`.
  For affinity they include `kd_mean` (M), `binding`, `binding_strength`, `expression`, `fit_quality` and
  `positive_control`. The partner guide requires BYOK ("you must not 'bundle' user orders under your own key") and
  sends resellers to the Partner Program. The homepage says "From $149 / protein".
- **Materials Project.** A key is required. An unauthenticated `GET /materials/summary/` answered 401
  `{"message":"No API key found in request"}` on 14 Oct 2026. The header is `X-API-KEY`. Every document carries a
  licence, `BY-C` or `BY-NC`. Knos asks only for `license=BY-C`, because it is a commercial service, and cites the
  Materials Project. The fixture holds the legacy site's mp-149 values (band gap 0.853 eV, energy above hull 0), not
  an API answer.
- **PCBWay.** Auth is the header `api-key`. A call without it answered 401 "need add api-key header to your http
  request" on 14 Oct 2026. The calls are `PcbQuotation`, `PlaceOrder` ("Add to Cart") and `ConfirmOrder`.
  `ConfirmOrder` pays from the partner's account balance (`PayType` 1, billed monthly) or on PCBWay's web page (2).
  `CheckOrderDetails` and `QueryOrderProcess` report which fabrication processes are done. PCBWay has no x402.
  `api-partner.pcbway.com` is called a test environment on its own help page; ask PCBWay for the production host.
- **JLCPCB.** The gateway is `https://open.jlcpcb.com`. Requests are signed with HMAC-SHA256 in
  `Authorization: JOP appid=...,accesskey=...,nonce=...,timestamp=...,signature=...` (api.jlcpcb.com/docs). Endpoint
  paths appear only in the developer console after approval, so the adapter stays a stub.
- **Xometry.** The developer API covers jobs, offers and webhooks for manufacturing partners, with no quote or order
  call. Buyers order through its CAD add-ins or enterprise PunchOut. Craftcloud (3D printing) publishes a buyer API
  (`api.craftcloud3d.com/api-docs.json`: price, offer, cart, order, order status), but it declares no auth scheme.
  It is the next mechanical rail to check.
- **PyLabRobot.** The latest stable release is 0.2.2 (PyPI, 30 Jul 2026), pinned here; 1.0.0b1 renames modules.
  `LiquidHandlerChatterboxBackend` with `set_volume_tracking(True)` tracks every aspiration and dispense. The example
  in `examples/labs/robotics/` shows a 1:2 serial dilution and its sealed test. The correct protocol ends 0.0 uL off
  in both re-runs; the buggy one (50 uL moved instead of 100) runs fine and ends 50 uL off, so the LAB verdict passes
  and the OUTCOME verdict fails.
  **By default Knos uses the recorded runs** (`src/knos/labs/fixtures/pylabrobot.json`, labelled FIXTURE: real
  PyLabRobot 0.2.2 runs of the two examples, keyed by the protocol's and sealed test's sha256; any other protocol is
  refused, never invented). To run the simulator yourself, use one command, which installs into its own venv and does
  not touch Knos:

  ```text
  sh scripts/install_pylabrobot.sh                 # makes ~/.knos/pylabrobot-venv, prints the next line
  export KNOS_PYLABROBOT_PYTHON=~/.knos/pylabrobot-venv/bin/python
  python -m knos.labs try pylabrobot --live         # the example on the real simulator
  python scripts/labs_pylabrobot_check.py           # live runs compared with the recording (exit 0 = same)
  ```

Try any lab on its fixtures with `python -m knos.labs try LAB`, where LAB is adaptyv, b12_selenium, b12_foundry,
materials_project, pcbway, xometry or pylabrobot. - **b12.** Selenium Route Search has quote, submit (with
`Idempotency-Key`), status and routes endpoints, priced in credits. The price of a credit is not published, so Knos
quotes credits, not USD.

The Foundry is ordered by e-mail (founders@b12-labs.com). Compound sourcing with full documented APIs exists at Molport
(api.molport.com/openapi.json) and Mcule (doc.mcule.com); either is the next chemistry rail. IBM RXN is not used: its
README says the hosted service reaches end of service on 28 Oct 2026.

## Two verdicts, because labs accept only this

| Verdict | Question | PASS | FAIL |
|---|---|---|---|
| **LAB** | Was the protocol executed as specified, was every run reported (failed ones included), and did QC pass? | the price goes to the lab and the 3% Knos lab order fee to the treasury, **even if the science failed** | everything goes back to the funder, and no fee is taken |
| **OUTCOME** | Did the result meet the researcher's claim? Given only after a LAB PASS; otherwise VOID. | the reward goes to the researcher, and the claim can graduate | the reward goes back to the funder, and the researcher is not paid |

Control runs are the lab's QC and never count as the researcher's result. Each verdict binds the evidence hash: the
runs, the QC, the protocol as executed, and every raw file's sha256. Each verdict is signed by **2 of 3** referee keys
(ed25519) over its order, evidence hash, spec hash, verdict, amount, recipient, mint, expiry and nonce.

`verdicts.check` refuses m-1 signatures, a key outside the set, the same key twice, an expired verdict, a spent nonce,
and a changed amount or recipient. A verdict it accepts is **spent**: its (order, nonce) is written to a persistent
store (`<Knos home>/labs/verdicts-spent.jsonl`, or `KNOS_LAB_VERDICTS_SPENT`), so the same verdict is refused the second
time, also in another process.

It follows the rule of V34PAY's verdict store: a refusal spends nothing, and `record=False` is a dry run.

The referees' keys never sit in the buyer's folder. `python -m knos.labs.devnet` takes them from `--referees`, and it
refuses that folder when it is the buyer's `--wallets` folder or inside it, or when the funder's key is one of them.

In the demo all three referee keys are on one machine, so they are not independent re-runners; the output says so.
Once V34PAY publishes a referee registry, the keys come from it. The devnet run covers every field it lists:
proteins, electronics, materials, chemistry and robotics.

It writes its output after every field, so a field that fails never loses the ones that ran.

The fee comes from `config/fees.yaml` (`fees.lab_order`, decided 14 Oct 2026: 300 bps). The decision does not say who
bears it. The demo charges it to the funder on top of the price.

## The escrow on devnet, and its limits

Each order has two pots: SPL token accounts owned by an **SPL Token multisig of the referee keys (2 of 3)**. No single
key can move them, the funder's included. A release is a token transfer that two referees co-sign.

It sits in one transaction with a Memo holding the signed verdict's digest, so the chain ties each release to its
verdict.

Limits: the chain does not read the verdict's fields, and it does not refund by itself after a deadline (the referees
sign the refund). The production path is knos_pay's m-of-n referee-verdict release (TASK-V0334), which checks expiry and
replay on chain. Once it is deployed, the same verdict messages release a knos_pay order.

The fee then follows knos_pay: 0.30% on chain, with the rest of the 3% invoiced (`cfg.platform("lab_order", amount)`).

### Shown on devnet, 14 Oct 2026 (`web/labs_devnet.json`, `python -m knos.labs.devnet`)

Test mint of the demo's own; referees' multisig; lab replies from fixtures (SYNTHETIC science).

| Field | Fund both pots | LAB PASS: lab paid + fee | x402 | OUTCOME FAIL: reward back, researcher 0 |
|---|---|---|---|---|
| proteins (Adaptyv fixture) | `2hXSLBMh5J7wvgpZDpkSyqDwnBj41ncAiJwQfKWRiSmxYzWtgigzXj4HHeGSvVet4vFVoenWMCYYeJeFmGHnQPbN` | `59wopRabZ4KRX7yviUKB2C2yTcKochwPR4JBj61G7gk1sJixWUrcCWhqvLB7aCSfEpbPLWC4Y8m2Qcc5hy6qAXhv` | Base Sepolia payload built; the x402.org facilitator's `/verify` simulated it and refused only for balance (`invalid_exact_evm_insufficient_balance`) | `myPdzaweKiqa3vMAcpEsHqicgL6jYcyNdtPtoiesSHdyRrqvqXbM94VWWm7o7cK4DJPYsn53iP5UizFjhvFaVDt` |
| electronics (PCBWay fixture + bench test) | `645D13zyqAUqX4PydiLFaW5yc1W9VGUmFQcYWmiDUgV4WNQEvA1JvMEm1YQty4bJUpccNVixDT8nA5DTDACeWmuN` | `2bL1Mje5FxijVa5WG8V6eLsFzRMYckHoMCrnN4fnGhepmYEeRfKp87K9F4Zgxvsbf5CJGFQeoD2chhdw7MFdPohC` | Solana devnet `exact`, settled by the x402.org facilitator: `4LiWaf9A884YNYWKvW4YKvyr9tjmMdpNk29ME5n8AyD3aKTa8vEzJ92QTzkb4V8qW3QkKPfdPuBpiScALaJbNjV3` | `2EfcAZmZgrFSjYk6UktVKQoyWhjQwYssA2CqiWowjfsRmmrrQwwYk3TZ6tskW4KsKY2NwyquH7jGJR9cRnfCfC4m` |

Balances read after the runs (test units): the proteins lab got 1,060.00, the electronics lab 55.00, the Knos treasury
33.45 (both 3% fees), and both researchers 0.

In electronics, the release went to a one-time payment wallet. That wallet then paid the lab stand-in's 402 through
the facilitator, because x402 `exact` needs a single-key payer and the pot is a multisig. With knos_pay's verdict path,
the escrow pays `payTo` directly.

## x402 on both chains (`knos.labs.x402pay`)

The lab's 402 names the network. Knos pays `eip155:84532` (Base Sepolia USDC `0x036CbD53842c5426634e7929541eC2318f3dCF7e`)
or `solana:EtWTRABZaYq6iMfeYKouRu166VU2xqa1` (devnet), and refuses mainnet until it is approved. EVM payloads are EIP-3009
`TransferWithAuthorization` signed over EIP-712, in pure Python.

Tests hold the code to published vectors: the signed example in the x402 spec recovers to its `from` address, and
EIP-712's own "Ether Mail" domain separator matches. Adaptyv's production rail is Base mainnet (`eip155:8453`). Whether
its sandbox runs on Base Sepolia is not documented.

## Private by default

Knos Record gets hashes (spec, evidence, order), timing (ordered, results, turnaround) and the two verdicts. It never
gets the results, sequences, protocol, buyer, price or the lab's name. The lab appears as `sha256(salt + lab)`, with a
fresh salt per order that only the buyer keeps, so nobody can count a lab's failures.

A lab's name goes in only with its consent (`lab_consents`), and results only with the buyer's opt-in (`publish`). Tests
check that no private value appears in the public line.

## Fiat (design only)

Labs and pharma refuse crypto-only settlement. The design: the same two pots, held in fiat by a licensed provider (card
or invoice in; payout to the lab's bank). The verdict messages are unchanged, and the provider releases on the same
2-of-3 signed verdict. Adaptyv already settles by Stripe hosted invoice and Stripe SPT.

PCBWay bills a partner account monthly. **Founder decision:** which provider holds fiat escrow and pays out (for
example Stripe Connect, or Airwallex through the US entity). Nothing here is built against a provider.

## Leitner re-verification (`src/knos/leitner/`, `config/leitner.yaml`)

Every verified claim, product, lab, agent and sealed test sits in a box. The boxes are 1, 3, 7 and 30 days, or
**orders** for labs: a new lab is checked on every order, a proven lab rarely. A pass moves the item up one box.

Any failure drops it to box 1 and **pauses its payouts and graduation** (`can_pay`) until it passes again. Sealed
tests that nobody fails in 20 runs rotate out. A test that caught a cheat stays hot for 10 more runs.

The money dashboard (`web/revenue/`) shows cost per verification before and after on a **SYNTHETIC** history. That
history has 60 items over 120 days, a seeded 15% that break once, and costs counted in re-runs. Re-checking everything
daily costs 1 re-run per item-day.

Leitner cost 0.0528 and still caught all 5 breakages, but later: 10.6 days unseen on average (22 at most), and 53
item-days in which a broken item could still have been paid. That is the trade-off the box intervals set. Shorter top
boxes buy faster catches with more re-runs.

The price of a re-run in USD has not been measured, so none is shown.

## What the founder does (Knos cannot: keys, accounts, applications)

1. **Adaptyv Partner Program** (Knos has not applied; this is the founder's step). Knos routes users' orders, so it is
   a platform. Apply at https://www.adaptyvbio.com/api/apply. The form asks for name, e-mail, role, company, website, team size, what the
   product does, modalities, monthly protein volume and assays. Suggested answers: "Knos holds each order's payment in
   escrow and releases it to the lab when the protocol and QC pass (a LAB verdict), independently of whether the design
   works; researchers keep their own key (BYOK)". Ask three questions:
   (a) can a machine-payment invoice be paid on delivery, so the LAB verdict releases it;
   (b) does the sandbox's x402 rail use Base Sepolia;
   (c) does `POST /api/v1/partners/mint-token` fit users who sign up through Knos.
   Until then, users bring their own token (portal: Organization, Settings, Tokens).
2. **Keys to make each adapter live** (none exists today): `ADAPTYV_API_KEY` (sandbox token from
   foundry.testing.adaptyvbio.com first), `MP_API_KEY` (free sign-in at next-gen.materialsproject.org, then the
   dashboard), `PCBWAY_API_KEY` (a partner key: e-mail anson@pcbway.com, per pcbway.com/api_cooperation.html; approval
   depends on "your company & business situation"; ask for the production host too), `B12_API_KEY` and the Selenium
   base URL (app.b12-labs.com), and a JLCPCB application at api.jlcpcb.com ("not all applications will be approved";
   support@jlcpcb.com).
3. **Fiat provider** for lab escrow (above).
4. **knos_pay verdict path**: once its upgrade is signed through the Squads vault (TASK-V0334), lab pots move from the
   referee multisig to knos_pay orders.

Sources were read on 14 Oct 2026 and are cited inline above and in each adapter's docstring.
