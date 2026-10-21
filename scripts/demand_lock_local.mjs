// The last step of the demand proof, on a local copy of the app (http://localhost:<port>): a test passkey (Chromium's
// virtual authenticator) signs in, the demand controls run a crossing, its brief is made Ready and opened ("Open and
// fund"), and the project page shows the locked Ready brief with its Grounding (Qloo) line. Phone and desktop sizes.
// Local only: a passkey on the live app would be an account, which this run never makes.
//
//   node scripts/demand_lock_local.mjs [http://localhost:8765] [out dir for screenshots]
import { chromium } from "playwright";

const BASE = process.argv[2] || "http://localhost:8765";
const OUT = process.argv[3] || ".";
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(BASE)) throw new Error("local only: http://localhost:<port>");
const fails = [];
const ok = (cond, what, extra) => { console.log((cond ? "ok   " : "FAIL ") + what + (extra ? " " + JSON.stringify(extra) : "")); if (!cond) fails.push(what); };

const browser = await chromium.launch();
for (const [w, h] of [[375, 812], [1280, 800]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", { options: { protocol: "ctap2", transport: "internal", hasResidentKey: true,
    hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE + "/#research", { waitUntil: "domcontentloaded" });
  await page.click("#whoBtn");
  await page.fill("#pkName", `test ${w}`);
  await page.click("#pkNew");
  await page.waitForFunction(() => !/sign in/i.test(document.querySelector("#whoBtn").textContent), null, { timeout: 60000 });
  ok(true, `${w}: signed in with a test passkey (virtual authenticator, this local app only)`);
  await page.goto(BASE + "/#research");
  await page.waitForSelector("#demandOpts [data-f=age]", { state: "visible", timeout: 60000 });
  await page.fill("#idea", "a recovery shoe for marathon runners");
  await page.selectOption("#demandOpts [data-f=age]", "25_to_29");
  await page.fill("#demandOpts [data-f=near]", "Austin");
  await page.selectOption("#demandOpts [data-f=price_level]", "3");
  await page.click("#crossBtn");
  await page.waitForSelector("#toBrief", { timeout: 240000 });
  await page.locator("#outcome").screenshot({ path: `${OUT}/demand_lock_${w}_answers.png` });
  await page.click("#toBrief");
  await page.waitForSelector("#bName", { timeout: 60000 });
  await page.fill("#pTitle", "Recovery shoe for marathon runners").catch(() => {});
  await page.fill("#bName", "Recovery shoe sell-through in Austin");
  await page.fill("#bTarget", "200 pairs sold in 60 days on test_sell_through");
  await page.fill("#bCheck", "ci / test_sell_through");
  await page.waitForFunction(() => (document.querySelector("#bLabel") || {}).textContent === "Ready", null, { timeout: 60000 });
  await page.click("#bLock");
  await page.waitForFunction(() => /#projects=/.test(location.hash) && document.querySelector("#readyChip"), null, { timeout: 60000 });
  const got = await page.evaluate(() => ({ chip: document.querySelector("#readyChip").textContent, grounding: (document.querySelector("#grounding") || {}).textContent || "",
    hash: location.hash }));
  ok(got.chip === "Ready to fund", `${w}: the project opened on the Ready brief`, { chip: got.chip, project: got.hash.slice(10, 30) });
  ok(/Grounding \(Qloo\)/.test(got.grounding), `${w}: its Grounding (Qloo) line is on the project`, { grounding: got.grounding.slice(0, 160) });
  ok(/asked: .*age 25 to 29.*near Austin.*price level 3/.test(got.grounding), `${w}: the line names what was asked of Qloo`,
    { asked: got.grounding.slice(got.grounding.indexOf("asked")).slice(0, 120) });
  ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${w}: nothing runs off the side`);
  await page.locator("#grounding").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${OUT}/demand_lock_${w}_project.png` });
  ok(errors.length === 0, `${w}: no page errors`, errors.slice(0, 2));
  await ctx.close();
}
await browser.close();
console.log(fails.length ? `${fails.length} failed` : "all passed");
process.exit(fails.length ? 1 : 0);
