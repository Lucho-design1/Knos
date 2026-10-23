// test_paper_to_preorder, live, at 375x812 and 1280x800: 5 papers (DOI or arXiv id) from 5 fields go from the
// app's research form to pre-orders open and a brief marked "Ready to fund"; the median time from "Run the crossing"
// to "Ready" must be 60 s or less. Pre-orders open = Qloo's evidence set the verdict OPEN and the product page shows
// its pre-order box. The operator's key (KNOS_ADMIN_KEY, a header, never printed) lets this run past the per-address
// limits; the outside counter leaves such runs out.
//
//   KNOS_ADMIN_KEY=... node scripts/test_paper_to_preorder.mjs [https://knos.onrender.com] [out dir]
import { chromium } from "playwright";

const APP = process.argv[2] || "https://knos.onrender.com";
const OUT = process.argv[3] || ".";
const PAPERS = [
  ["biotech", "10.1038/nature16521", ""],                                              // a sweat sensor, Nature 2016
  ["materials", "10.1126/science.aam8743", ""],                                         // water from desert air, Science 2017
  ["sleep science", "10.1080/15402002.2017.1300587", "a sleep tracking ring"],          // a sleep ring against polysomnography
  ["biomechanics", "10.1007/s40279-017-0811-2", "a running shoe with carbon plate"],    // marathon shoes and running economy
  ["nutrition", "10.1093/ajcn/76.6.1207", "a smart kitchen scale for meal planning"],   // portion size and energy intake
];
const fails = [];
const ok = (c, what, extra) => { console.log((c ? "ok   " : "FAIL ") + what + (extra ? " " + JSON.stringify(extra) : "")); if (!c) fails.push(what); };
const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2; };

const browser = await chromium.launch();
for (const [w, h] of [[375, 812], [1280, 800]]) {
  const times = [];
  for (const [field, ref, product] of PAPERS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.setExtraHTTPHeaders({ "X-Knos-Admin": process.env.KNOS_ADMIN_KEY || "" });
    const page = await ctx.newPage();
    await page.goto(APP + "/#research", { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#ref", { state: "visible", timeout: 60000 });
    await page.fill("#ref", ref);
    if (product) await page.fill("#product", product);
    const t0 = Date.now();
    await page.click("#crossBtn");
    await page.waitForSelector("#toBrief", { timeout: 240000 });
    const open = await page.$("#outcome .decision.open a.button[href^='#buy=']");
    const buy = open ? await open.getAttribute("href") : null;
    ok(!!open, `${w} ${field} ${ref}: Qloo's evidence opened it`, { verdict: await page.textContent("#outcome .decision h3") });
    await page.click("#toBrief");
    await page.waitForSelector("#bName", { timeout: 60000 });
    await page.fill("#bName", `First production run: ${product || field}`);
    await page.fill("#bTarget", "200 units pre-ordered in 60 days on test_preorders");
    await page.fill("#bCheck", "ci / test_preorders");
    await page.waitForFunction(() => (document.querySelector("#bLabel") || {}).textContent === "Ready", null, { timeout: 60000 });
    const s = (Date.now() - t0) / 1000;
    times.push(s);
    ok(true, `${w} ${field}: brief Ready to fund, ${s.toFixed(1)} s from "Run the crossing"`);
    if (buy) {
      await page.goto(APP + "/" + buy, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#buyBox") && !document.querySelector("#buyBox").hidden, null, { timeout: 60000 }).catch(() => {});
      ok(await page.evaluate(() => !!document.querySelector("#buyBox") && !document.querySelector("#buyBox").hidden), `${w} ${field}: pre-orders open on its product page`);
      await page.screenshot({ path: `${OUT}/paper_${w}_${field.replace(/ /g, "_")}.png` });
    }
    await ctx.close();
  }
  const m = median(times);
  ok(m <= 60, `${w}: median ${m.toFixed(1)} s from paper to Ready (60 s at most)`, { times: times.map((x) => +x.toFixed(1)) });
}
await browser.close();
console.log(fails.length ? `FAIL test_paper_to_preorder (${fails.length})` : "PASS test_paper_to_preorder");
process.exit(fails.length ? 1 : 0);
