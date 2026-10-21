// M7 test_judge_path, live: what a judge does first. A fresh browser (no cache, no cookies, no sign-up) opens the front
// door's demand check, types an idea and presses Check; the time from the press to the verdict on screen must be
// 10 s or less, in each of 3 runs. Each run asks a different idea, so no answer is served from the browser's cache.
//
//   node scripts/judge_path.mjs [https://drexthealpha.github.io/Knos/] [out dir]
import { chromium } from "playwright";

const SITE = process.argv[2] || "https://drexthealpha.github.io/Knos/";
const OUT = process.argv[3] || ".";
const IDEAS = ["a plant-based burger chain", "a smart water bottle that glows to remind you to drink", "a true-crime podcast about art heists"];
const fails = [];
const ok = (c, what, extra) => { console.log((c ? "ok   " : "FAIL ") + what + (extra ? " " + JSON.stringify(extra) : "")); if (!c) fails.push(what); };

const browser = await chromium.launch();
const times = [];
for (const [i, idea] of IDEAS.entries()) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });   // a fresh profile each run: cold
  const page = await ctx.newPage();
  await page.goto(SITE + "#demand", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#fd-idea", { timeout: 30000 });
  ok(!(await page.$("input[type=password]")), `run ${i + 1}: no sign-up or password asked`);
  await page.fill("#fd-idea", idea);
  const t0 = Date.now();
  await page.click("#fd-go");
  await page.waitForSelector("#fd-out .card h3", { timeout: 60000 });
  const s = (Date.now() - t0) / 1000;
  times.push(s);
  const verdict = (await page.textContent("#fd-out .card h3")).trim();
  ok(s <= 10, `run ${i + 1}: "${idea}" verdict "${verdict}" in ${s.toFixed(1)} s (10 s at most)`);
  await page.screenshot({ path: `${OUT}/judge_path_${i + 1}.png` });
  await ctx.close();
}
await browser.close();
console.log(`times: ${times.map((x) => x.toFixed(1)).join(", ")} s`);
console.log(fails.length ? `FAIL test_judge_path (${fails.length})` : "PASS test_judge_path");
process.exit(fails.length ? 1 : 0);
