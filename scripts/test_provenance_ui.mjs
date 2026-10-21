// M3 test_provenance_ui, live, at 375x812 and 1280x800: 0 Qloo-derived values without a link to their trace.
// On the app's crossing outcome, the product page, the home cards, the front door's demand check and the "With and
// without Qloo" page: every [data-qloo] value holds a source link, and every link opens a trace that names the request
// (endpoint, params, entity/tag ids, no key), a result excerpt and the limit. As an audit, every Qloo value of the
// report (cities, segments, matches, families' answers) that is on screen must sit inside a [data-qloo] element.
//
//   node scripts/test_provenance_ui.mjs [https://knos.onrender.com] [https://drexthealpha.github.io/Knos/] [out dir]
import { chromium } from "playwright";

const APP = process.argv[2] || "https://knos.onrender.com";
const SITE = process.argv[3] || "https://drexthealpha.github.io/Knos/";
const OUT = process.argv[4] || ".";
const IDEA = "a smart water bottle that glows to remind you to drink";
const fails = [];
const ok = (c, what, extra) => { console.log((c ? "ok   " : "FAIL ") + what + (extra ? " " + JSON.stringify(extra) : "")); if (!c) fails.push(what); };
const traces = new Map();

async function trace(href) {                       // the trace a link opens, and whether it holds what it must
  const u = new URL(href, APP);
  const h = u.searchParams.get("hash");
  if (!traces.has(h)) traces.set(h, await (await fetch(`${APP}/api/trace?hash=${h}`)).json());
  const t = traces.get(h);
  const n = u.hash.startsWith("#call-") ? Number(u.hash.slice(6)) : null;
  const calls = n ? (t.calls || []).filter((c) => c.n === n) : t.calls || [];
  const good = !!t.hash && /not causal|not a cause/.test(t.limit || "") && /aggregate/.test(t.limit || "") && /any one person|about a person/.test(t.limit || "")
    && (t.without_qloo || calls.length > 0) && calls.every((c) => c.endpoint && c.params && typeof c.excerpt === "string")
    && !/x-api-key|QLOO_API_KEY/i.test(JSON.stringify(t));
  return { good, h, n, calls: calls.length };
}

async function audit(page, where) {
  const got = await page.evaluate(() => [...document.querySelectorAll("[data-qloo]")].filter((e) => e.offsetParent !== null || e.closest("details"))
    .map((e) => ({ text: e.textContent.trim().slice(0, 60), href: (e.querySelector("a[data-trace]") || {}).href || null })));
  const bare = got.filter((x) => !x.href);
  ok(got.length > 0 && bare.length === 0, `${where}: ${got.length} Qloo-derived values, ${bare.length} without a source link`, bare.slice(0, 3));
  const checked = await Promise.all([...new Set(got.map((x) => x.href).filter(Boolean))].map(trace));
  const broken = checked.filter((x) => !x.good);
  ok(checked.length > 0 && broken.length === 0, `${where}: ${checked.length} source links open a trace with the request, the result and the limit`, broken.slice(0, 3));
  return got.length;
}

async function unmarked(page, where, values) {      // Qloo values on screen outside any [data-qloo]
  const loose = await page.evaluate((vals) => {
    const out = [];
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const p = n.parentElement;
      if (!p || p.closest("[data-qloo], script, style, #steps details, textarea, select, option, input")) continue;
      for (const v of vals) if (v.length > 3 && n.textContent.includes(v)) out.push(v);
    }
    return [...new Set(out)];
  }, values);
  ok(loose.length === 0, `${where}: no Qloo value on screen outside a sourced element`, loose.slice(0, 5));
}

const browser = await chromium.launch();
for (const [w, h] of [[375, 812], [1280, 800]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  // 1. the app: a crossing, then its outcome and its live Qloo steps
  await page.goto(APP + "/#research", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#idea", { state: "visible", timeout: 60000 });
  await page.fill("#idea", IDEA);
  await page.click("#crossBtn");
  await page.waitForSelector("#toBrief", { timeout: 240000 });
  const hash = await page.evaluate(() => (document.querySelector("#outcome a[data-trace]") || {}).href || "");
  const rep = await (await fetch(`${APP}/api/report?hash=${new URL(hash, APP).searchParams.get("hash")}`)).json();
  const values = [...(rep.cities || []).map((c) => c.name), ...((rep.decision || {}).plan ? rep.decision.plan.who.segments || [] : []),
    ...Object.values(rep.families || {}).flatMap((f) => (f.answer || []).map((a) => a.name))].filter(Boolean);
  await audit(page, `${w} app crossing`);
  await unmarked(page, `${w} app crossing`, values);
  await page.screenshot({ path: `${OUT}/provenance_${w}_crossing.png` });
  // 2. the product page of that report
  await page.goto(`${APP}/#buy=${rep.hash}`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#productCard [data-qloo]", { timeout: 60000 });
  await audit(page, `${w} product page`);
  await unmarked(page, `${w} product page`, values);
  // 3. the home cards (their launch cities are Qloo's)
  await page.goto(APP + "/#home", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);
  const cards = await page.$$eval(".hp-card [data-qloo]", (x) => x.length);
  if (cards) await audit(page, `${w} home cards`);
  else ok(true, `${w} home cards: no Qloo value shown on the cards`);
  // 4. the "With and without Qloo" page
  await page.goto(APP + "/with-without", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#ww tbody tr", { timeout: 60000 });
  await audit(page, `${w} with-without page`);
  // 5. the trace page itself: request, ids, result, limit; no key
  await page.goto(`${APP}/trace.html?hash=${rep.hash}#call-1`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".tr-call", { timeout: 60000 });
  const tp = await page.evaluate(() => ({ calls: document.querySelectorAll(".tr-call").length, text: document.body.innerText }));
  ok(tp.calls > 0 && /Request/.test(tp.text) && /Result/.test(tp.text) && /not causal/.test(tp.text) && !/x-api-key/i.test(tp.text),
    `${w} trace page: ${tp.calls} calls, each with its request, result and limit, no key`);
  ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${w} trace page: nothing runs off the side`);
  await page.screenshot({ path: `${OUT}/provenance_${w}_trace.png` });
  // 6. the front door's demand check
  await page.goto(SITE + "#demand", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#fd-idea", { timeout: 60000 });
  await page.fill("#fd-idea", IDEA);
  await page.click("#fd-go");
  await page.waitForSelector("#fd-out .card [data-qloo]", { timeout: 120000 });
  await audit(page, `${w} front door #demand`);
  await page.screenshot({ path: `${OUT}/provenance_${w}_front.png` });
  await ctx.close();
}
await browser.close();
console.log(fails.length ? `FAIL test_provenance_ui (${fails.length})` : "PASS test_provenance_ui");
process.exit(fails.length ? 1 : 0);
