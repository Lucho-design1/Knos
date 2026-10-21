// The screenshots of SUBMISSION.md, from the live app, signed out (no credential, no personal data on screen):
// the crossing's outcome with its source links, a trace, a paper's product open for pre-orders, and the table.
//
//   node scripts/submission_shots.mjs [https://knos.onrender.com] [docs/submission]
import { chromium } from "playwright";

const APP = process.argv[2] || "https://knos.onrender.com";
const OUT = process.argv[3] || "docs/submission";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

await page.goto(APP + "/#research", { waitUntil: "domcontentloaded" });
await page.waitForSelector("#idea", { state: "visible", timeout: 60000 });
await page.fill("#idea", "a smart water bottle that glows to remind you to drink");
await page.click("#crossBtn");
await page.waitForSelector("#toBrief", { timeout: 240000 });
await page.locator("#outcome").scrollIntoViewIfNeeded();
await page.locator("#outcome").screenshot({ path: `${OUT}/crossing.png` });
const hash = new URL(await page.$eval("#outcome a[data-trace]", (a) => a.href)).searchParams.get("hash");

await page.goto(`${APP}/trace.html?hash=${hash}`, { waitUntil: "domcontentloaded" });
await page.waitForSelector(".tr-call", { timeout: 60000 });
await page.screenshot({ path: `${OUT}/trace.png` });

await page.goto(`${APP}/#research`, { waitUntil: "domcontentloaded" });
await page.waitForSelector("#ref", { state: "visible", timeout: 60000 });
await page.fill("#ref", "10.1038/nature16521");
await page.click("#crossBtn");
await page.waitForSelector("#outcome .decision.open a.button", { timeout: 240000 });
await page.click("#outcome .decision.open a.button");
await page.waitForSelector("#productCard [data-qloo]", { timeout: 60000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/paper_open.png` });

await page.goto(`${APP}/with-without`, { waitUntil: "domcontentloaded" });
await page.waitForSelector("#ww tbody tr", { timeout: 60000 });
await page.screenshot({ path: `${OUT}/with_without.png` });
await browser.close();
console.log("wrote 4 screenshots to " + OUT);
