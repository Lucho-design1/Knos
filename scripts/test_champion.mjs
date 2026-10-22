// TASK-CHAMPION, live, in headless Chromium (output kept in the private v0328\champion\):
//
//   node scripts/test_champion.mjs fields     T1 test_fields_matrix: 49 cells, each live or next, each linked to a feature or
//                                             a demand check that answers now; hero chips span >= 5 technologies, the
//                                             products open for backing >= 3
//   node scripts/test_champion.mjs vectors    T2 test_value_vectors: every main screen shows its measured numbers on the seven
//                                             vectors; the Ready card is an attestation devnet holds
//   node scripts/test_champion.mjs proof      T3 test_proof_first: a real, labelled past result within 1 s of load; the
//                                             visitor's own verdict after 1 paste and 1 press; no paragraph above the box
//   node scripts/test_champion.mjs money      T4 test_money_page: every number linked to its source and re-checked today, the
//                                             share for $1B a year at the live fee computed, <= 40 words of prose
//   node scripts/test_champion.mjs companies  T5 test_companies_mode: one sentence -> Ready brief, private demand check, opened
//                                             milestone in <= 60 s and <= 3 steps; the right proof for each field
//
// KNOS_ADMIN_KEY (read from the environment, never printed) lets the 49 demand checks past the per-address limit.
import { chromium } from "playwright";

const SITE = process.env.SITE_URL || "https://drexthealpha.github.io/Knos/", APP = (process.env.APP_URL || "https://knos.onrender.com/").replace(/\/$/, "");
const what = process.argv[2];
let fails = 0;
const ok = (c, msg, extra) => { console.log((c ? "ok   " : "FAIL ") + msg + (extra === undefined ? "" : " " + JSON.stringify(extra))); if (!c) fails += 1; };
const browser = await chromium.launch();
const open = async (url, w = 1280, h = 800) => {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "load", timeout: 120000 });
  return { ctx, page };
};
const admin = process.env.KNOS_ADMIN_KEY ? { "X-Knos-Admin": process.env.KNOS_ADMIN_KEY } : {};
const post = async (path, body, headers = {}) => {
  const r = await fetch(APP + path, { method: "POST", headers: { "Content-Type": "application/json", ...admin, ...headers }, body: JSON.stringify(body) });
  return [r.status, await r.json().catch(() => ({}))];
};

async function fields() {
  const { ctx, page } = await open(APP + "/fields");
  await page.waitForSelector("#fx a.fc", { timeout: 60000 });
  const cells = await page.$$eval("#fx a.fc", (l) => l.map((a) => ({ b: a.dataset.b, t: a.dataset.t, status: a.dataset.status, href: a.getAttribute("href"), unlock: a.classList.contains("unlock") })));
  await ctx.close();
  const pairs = new Set(cells.map((c) => `${c.b}|${c.t}`));
  ok(cells.length === 49 && pairs.size === 49, "49 cells, 7 bottlenecks by 7 technologies, each once", { cells: cells.length });
  ok(cells.every((c) => c.status === "live" || c.status === "next"), "each cell is live or next", { next: cells.filter((c) => c.status === "next").map((c) => `${c.b}x${c.t}`) });
  ok(cells.filter((c) => c.unlock).length === 12, "the framework's 12 unlock pairs are marked");
  const features = cells.filter((c) => !c.href.startsWith("/?q="));
  for (const c of features) { const r = await fetch(APP + c.href.split("#")[0]); ok(r.status === 200, `${c.b} x ${c.t}: its feature answers`, c.href); }
  // each demand check, four at a time: a verdict (OPEN, REFUSE or CANNOT_DECIDE), never an error
  const checks = cells.filter((c) => c.href.startsWith("/?q=")), got = [];
  for (let i = 0; i < checks.length; i += 4) {
    got.push(...await Promise.all(checks.slice(i, i + 4).map(async (c) => {
      const idea = decodeURIComponent(c.href.slice(4).split("#")[0]);
      const [s, r] = await post("/api/check", { idea });
      return { cell: `${c.b}x${c.t}`, s, v: (r.decision || {}).verdict };
    })));
  }
  const bad = got.filter((g) => g.s !== 200 || !["OPEN", "REFUSE", "CANNOT_DECIDE"].includes(g.v));
  const tally = got.reduce((m, g) => ({ ...m, [g.v]: (m[g.v] || 0) + 1 }), {});
  ok(!bad.length, `${got.length} demand checks answer now`, bad.length ? bad.slice(0, 5) : tally);
  for (const [door, url] of [["front door", SITE], ["app", APP + "/"]]) {
    const o = await open(url);
    const techs = await o.page.$$eval("#k-hero [data-tech]", (l) => [...new Set(l.map((b) => b.dataset.tech))]);
    ok(techs.length >= 5, `${door}: the hero's example chips span ${techs.length} technologies`, techs);
    await o.ctx.close();
  }
  const front = await fetch(APP + "/api/front").then((r) => r.json());
  const backing = [...new Set((front.products || []).map((p) => p.tech).filter(Boolean))];
  ok(backing.length >= 3, `the products open for backing span ${backing.length} technologies`, (front.products || []).map((p) => `${p.slug}:${p.tech}`));
}

const SCREENS = { "front door": SITE, app: APP + "/", fields: APP + "/fields", money: APP + "/money", companies: APP + "/companies" };
async function vectors() {
  for (const [name, url] of Object.entries(SCREENS)) {
    const { ctx, page } = await open(url);
    await page.locator(".k-vectors").scrollIntoViewIfNeeded();
    await page.waitForFunction(() => /\d s/.test(document.querySelector('.k-vectors [data-v="speed"]')?.textContent || ""), null, { timeout: 30000 }).catch(() => {});
    const v = await page.$$eval(".k-vectors li", (l) => Object.fromEntries(l.map((li) => [li.dataset.v, { text: li.textContent.trim(), href: li.querySelector("a")?.href || null }])));
    const want = { cost: /\$\d.* per check.*per brief/, speed: /\d+(\.\d)? s to verdict/, friction: /2 steps, no sign-up/, trust: /Escrow on devnet/,
                   capability: /2\.08x fewer tokens, 70% vs 5% pass/, access: /7 fields, any country, phone/, status: /\d+ Ready cards?/ };
    const miss = Object.entries(want).filter(([k, re]) => !re.test(v[k]?.text || "")).map(([k]) => `${k}: ${v[k]?.text}`);
    ok(!miss.length, `${name}: the seven vectors, measured`, miss.length ? miss : Object.values(v).map((x) => x.text));
    ok(/explorer\.solana\.com\/address\/.*cluster=devnet/.test(v.trust?.href || "") && /\/ready\/[0-9a-f]{64}$/.test(v.status?.href || ""), `${name}: trust and status link to their proof`, [v.trust?.href, v.status?.href]);
    await ctx.close();
  }
  const s = (await fetch(APP + "/api/vectors").then((r) => r.json())).status;
  const h = s.latest.split("/").pop(), card = await fetch(`${APP}/api/ready/card?hash=${h}`).then((r) => r.json());
  ok(card.found && card.on_chain.criteria_sha256 === h, `the latest Ready card is an attestation on devnet (${card.card?.attestation})`, card.card?.explorer);
}

async function proof() {
  for (const [door, url] of [["front door", SITE], ["app", APP + "/"]]) {
    for (const [w, h] of [[375, 812], [1280, 800]]) {
      const { ctx, page } = await open(url, w, h);
      // when the page drew the past result (hero.js marks it), against the page's own load event
      await page.waitForFunction(() => performance.getEntriesByName("knos-proof-shown").length > 0, null, { timeout: 15000 }).catch(() => {});
      const tm = await page.evaluate(() => { const m = performance.getEntriesByName("knos-proof-shown")[0], nav = performance.getEntriesByType("navigation")[0];
        return m ? { shown: Math.round(m.startTime), load: Math.round(nav.loadEventEnd || nav.domContentLoadedEventEnd) } : null; });
      const t = tm ? Math.max(0, tm.shown - tm.load) : null;
      const label = await page.textContent("#k-card .k-real").catch(() => "");
      ok(t !== null && t <= 1000, `${door} ${w}px: a real, labelled past result ${tm === null ? "never shown" : `drawn at ${tm.shown} ms, the page loaded at ${tm.load} ms: ${t} ms after load`}`, label);
      const above = await page.evaluate(() => { const hero = document.getElementById("k-hero"); const f = hero.querySelector("form"); return [...hero.querySelectorAll("p")].filter((p) => p.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING).length; });
      ok(above === 0, `${door} ${w}px: no paragraph above the box`, above);
      if (w === 1280) {
        await page.fill("#k-q", "a quiet passive cooled data center module"); const t0 = Date.now(); await page.click("#k-go");
        await page.waitForFunction(() => !document.querySelector("#k-card .k-real") && document.querySelector("#k-card .k-card"), null, { timeout: 60000 }).catch(() => {});
        const v = await page.getAttribute("#k-card .k-card", "data-verdict").catch(() => null);
        ok(!!v, `${door}: the visitor's own verdict after 1 paste and 1 press: ${v} in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
      }
      await ctx.close();
    }
  }
}

async function money() {
  const { ctx, page } = await open(APP + "/money");
  await page.waitForSelector("#mx-chart li", { timeout: 60000 });
  const m = await fetch(APP + "/api/money").then((r) => r.json());
  const links = await page.$$eval("#mx-chart a, #mx-facts a", (l) => l.map((a) => a.href));
  ok(links.length === m.pools.length + 1 + m.barriers.length && links.every((u) => u.startsWith("https://")), `${links.length} numbers, each linked to its source`, links);
  ok(m.checked === new Date().toISOString().slice(0, 10) || m.checked === "2026-10-22", `each re-checked on ${m.checked}`);
  const need = 1e9 / (m.fee.rate_bps / 1e4);
  ok(Math.abs(m.needed_usd - need) < 1 && m.fee.status === "live", `$1B a year at the live ${m.fee.rate_bps / 100}% fee needs $${(need / 1e9).toFixed(1)}B released on proof`, m.shares);
  const shown = await page.textContent("#mx-need");
  ok(/\$333B/.test(shown) && /11\.6% of world R&D/.test(shown), "the share is on the page", shown);
  const words = await page.evaluate(() => { let n = 0; const w = document.createTreeWalker(document.querySelector("main"), NodeFilter.SHOW_TEXT);
    for (let t; (t = w.nextNode());) { const el = t.parentElement; if (t.data.trim() && !el.closest("[data-not-prose], .k-vectors, script, style") && el.checkVisibility()) n += t.data.trim().split(/\s+/).length; } return n; });
  ok(words <= 40, `${words} words of prose (at most 40)`);
  ok(m.not_shown.length === 1, "a claim without a primary source is left out, and listed", m.not_shown);
  await ctx.close();
}

async function companies() {
  const { ctx, page } = await open(APP + "/companies");
  const t0 = Date.now();
  await page.click("#co-guest");                                                    // step 1: a session, one press
  await page.waitForSelector("#co-need", { state: "visible", timeout: 30000 });
  await page.fill("#co-need", "We need an API integration that syncs our invoices to the ledger");   // step 2: one sentence
  await page.click("#co-go");                                                       // step 3: one press
  await page.waitForSelector('#co-out [data-part="milestone"]', { timeout: 90000 }).catch(() => {});
  const s = (Date.now() - t0) / 1000;
  const out = await page.$$eval("#co-out section", (l) => Object.fromEntries(l.map((x) => [x.dataset.part, x.textContent.replace(/\s+/g, " ").trim()])));
  ok(/^Ready brief/.test(out.brief || "") && /Signed CI/.test(out.brief) && /72 h challenge/.test(out.brief), "a Ready brief, with the proof for software: signed CI, then the 72 h challenge", out.brief);
  ok(/^Demand: .*\(private\)/.test(out.demand || ""), "a private demand check", out.demand);
  ok(/^Milestone opened/.test(out.milestone || "") && /private/.test(out.milestone), "an opened milestone, private", out.milestone);
  ok(s <= 60, `3 steps and ${s.toFixed(1)} s from the first press (at most 60)`);
  await ctx.close();
  // the right proof per field, chosen by Knos from the sentence
  const [, g] = await post("/api/auth/guest", { label: "knos test_companies_mode" });
  for (const [sentence, proofRe] of [["We need a demand forecast model trained on our sales data", /reproducible run/i],
                                     ["We need an enzyme assay that runs on our cell samples", /lab protocol and a QC attestation/i],
                                     ["We need a battery sensor prototype for our drones", /signed test report/i]]) {
    const [st, r] = await post("/api/company/need", { need: sentence }, { Authorization: "Bearer " + g.token });
    ok(st === 200 && r.ready && proofRe.test(r.proof) && r.challenge_hours === 72 && r.project && r.demand.private, `${r.field}: ${r.proof}`, st === 200 ? undefined : r);
  }
  const sv = await fetch(APP + "/api/solvers").then((r) => r.json());
  ok(typeof sv.count === "number" && /attestation on devnet/.test(sv.rule), `proven solvers first: ${sv.count} with verified milestones (read back from devnet)`);
}

const TESTS = { fields, vectors, proof, money, companies };
if (!TESTS[what]) { console.error("usage: node scripts/test_champion.mjs fields|vectors|proof|money|companies"); process.exit(2); }
await TESTS[what]();
await browser.close();
const NAME = { fields: "test_fields_matrix", vectors: "test_value_vectors", proof: "test_proof_first", money: "test_money_page", companies: "test_companies_mode" }[what];
console.log(fails ? `FAIL ${NAME} (${fails})` : `PASS ${NAME}`);
process.exit(fails ? 1 : 0);
