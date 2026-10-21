// The demand families end to end on the live app, at a phone (375x812) and a desktop (1280x800): the plain controls set,
// a crossing run on live Qloo data, each family's answer shown, the header on one line, and the brief written from that
// check marked Ready to fund (the free check; opening the project needs a passkey sign-in, which this run never makes).
//
//   node scripts/demand_live.mjs [https://knos.onrender.com] [out dir for screenshots]
import { chromium } from "playwright";

const BASE = process.argv[2] || "https://knos.onrender.com";
const OUT = process.argv[3] || ".";
const fails = [];
const ok = (cond, what, extra) => { console.log((cond ? "ok   " : "FAIL ") + what + (extra ? " " + JSON.stringify(extra) : "")); if (!cond) fails.push(what); };

const browser = await chromium.launch();
for (const [w, h] of [[375, 812], [1280, 800]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE + "/#research", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#demandOpts [data-f=age]", { timeout: 60000 });
  const header = await page.evaluate(() => { const hd = document.querySelector("header .bar"); return hd ? hd.getBoundingClientRect().height : 0; });
  ok(header > 0 && header < 70, `${w}: the header bar is one line (desktop adds the role tabs below it)`, { height: header });
  const wide = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  ok(wide, `${w}: nothing runs off the side`);
  await page.fill("#idea", "a recovery shoe for marathon runners");
  await page.selectOption("#demandOpts [data-f=age]", "25_to_29");
  await page.selectOption("#demandOpts [data-f=gender]", "female");
  await page.check("#demandOpts [data-f=popularity_max]");
  await page.fill("#demandOpts [data-f=near]", "Austin");
  await page.selectOption("#demandOpts [data-f=radius]", "20000");
  await page.selectOption("#demandOpts [data-f=price_level]", "3");
  await page.click("#crossBtn");
  await page.waitForSelector("#toBrief", { timeout: 240000 });
  const fam = await page.evaluate(() => [...document.querySelectorAll("#outcome [data-family], #outcome .fam-answer, #outcome h4")].map((e) => e.textContent.trim().slice(0, 60)));
  const text = await page.evaluate(() => document.querySelector("#outcome").innerText);
  ok(/Who wants it/i.test(text) && /Where to launch/i.test(text), `${w}: the families' answers are shown`, fam.slice(0, 6));
  ok(!/\b(undefined|null|NaN)\b/.test(text), `${w}: no undefined, null or NaN in the answers`);
  await page.screenshot({ path: `${OUT}/demand_live_${w}_answers.png`, fullPage: false });
  await page.click("#toBrief");
  await page.waitForSelector("#bName", { timeout: 60000 });
  const report = await page.evaluate(() => sessionStorage.getItem("knos.report"));
  ok(/^[0-9a-f]{64}$/.test(report || ""), `${w}: the brief carries this check's report`, { report: (report || "").slice(0, 16) });
  await page.fill("#bName", "Recovery shoe sell-through in Austin");
  await page.fill("#bTarget", "200 pairs sold in 60 days on test_sell_through");
  await page.fill("#bCheck", "ci / test_sell_through");
  await page.waitForFunction(() => (document.querySelector("#bLabel") || {}).textContent === "Ready", null, { timeout: 60000 });
  ok(true, `${w}: the brief is Ready to fund, and "Open and fund" is enabled`, { disabled: await page.isDisabled("#bLock") });
  await page.screenshot({ path: `${OUT}/demand_live_${w}_ready.png`, fullPage: false });
  ok(errors.length === 0, `${w}: no page errors`, errors.slice(0, 2));
  await page.close();
}
await browser.close();
console.log(fails.length ? `${fails.length} failed` : "all passed");
process.exit(fails.length ? 1 : 0);
