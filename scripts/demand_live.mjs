// The demand families end to end on the live app, at a phone (375x812) and a desktop (1280x800): the plain controls set,
// a crossing run on live Qloo data, each family's answer shown, the header on one line, and the brief written from that
// check marked Ready to fund.
//
// With --lock it goes on into the locked Ready brief: a guest session (the app's own unverified label: no password, no
// passkey, no account record) presses "Open and fund", and the project's page must say "Ready to fund" with its
// Grounding (Qloo) line and what was asked; the API must say Ready with a criteria hash. The same guest, as the
// project's buyer, then archives it (POST /api/project/archive), so a proof run leaves nothing on the public list.
//
//   node scripts/demand_live.mjs [--lock] [https://knos.onrender.com] [out dir for screenshots]
import { chromium } from "playwright";

const args = process.argv.slice(2);
const LOCK = args.includes("--lock");
const [BASE = "https://knos.onrender.com", OUT = "."] = args.filter((a) => a !== "--lock");
const fails = [];
const ok = (cond, what, extra) => { console.log((cond ? "ok   " : "FAIL ") + what + (extra ? " " + JSON.stringify(extra) : "")); if (!cond) fails.push(what); };
const post = async (path, body, token) => (await fetch(BASE + path, { method: "POST", body: JSON.stringify(body),
  headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) } })).json();

const browser = await chromium.launch();
for (const [w, h] of [[375, 812], [1280, 800]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const guest = LOCK ? await post("/api/auth/guest", { label: "demand_live --lock proof run" }) : null;
  if (guest) await ctx.addInitScript((s) => { try { if (!localStorage.getItem("knos.session")) localStorage.setItem("knos.session", s); } catch (e) { /* none */ } }, JSON.stringify(guest));
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE + "/#research", { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#demandOpts [data-f=age]", { state: "visible", timeout: 60000 });
  const header = await page.evaluate(() => { const hd = document.querySelector("header .bar"); return hd ? hd.getBoundingClientRect().height : 0; });
  ok(header > 0 && header < 70, `${w}: the header bar is one line (desktop adds the role tabs below it)`, { height: header });
  const wide = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  ok(wide, `${w}: nothing runs off the side`);
  if (LOCK) ok(!/sign in/i.test(await page.textContent("#whoBtn")), `${w}: a guest session (unverified label) is in the page`);
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
  if (LOCK) await page.fill("#pTitle", "Proof run: recovery shoe (demand_live --lock, test)").catch(() => {});
  await page.fill("#bName", "Recovery shoe sell-through in Austin");
  await page.fill("#bTarget", "200 pairs sold in 60 days on test_sell_through");
  await page.fill("#bCheck", "ci / test_sell_through");
  await page.waitForFunction(() => (document.querySelector("#bLabel") || {}).textContent === "Ready", null, { timeout: 60000 });
  ok(!(await page.isDisabled("#bLock")), `${w}: the brief is Ready to fund, and "Open and fund" is enabled`);
  await page.screenshot({ path: `${OUT}/demand_live_${w}_ready.png`, fullPage: false });
  if (LOCK) {
    await page.click("#bLock");
    await page.waitForFunction(() => /#projects=/.test(location.hash) && document.querySelector("#readyChip"), null, { timeout: 90000 });
    const got = await page.evaluate(() => ({ chip: document.querySelector("#readyChip").textContent, id: location.hash.split("=")[1],
      grounding: (document.querySelector("#grounding") || {}).textContent || "" }));
    ok(got.chip === "Ready to fund", `${w}: the project opened on the locked Ready brief`, { chip: got.chip, project: got.id });
    ok(/Grounding \(Qloo\)/.test(got.grounding), `${w}: its Grounding (Qloo) line`, { grounding: got.grounding.slice(0, 160) });
    ok(/asked: .*age 25 to 29.*near Austin.*price level 3/.test(got.grounding), `${w}: the line names what was asked`,
      { asked: got.grounding.slice(got.grounding.indexOf("asked")).slice(0, 140) });
    const p = await (await fetch(`${BASE}/api/project?id=${got.id}`)).json();
    ok(p.ready && p.ready.ready === true && /^[0-9a-f]{64}$/.test(p.ready.criteria_hash || ""), `${w}: the API says Ready, with its criteria hash`,
      { criteria: (p.ready || {}).criteria_hash && p.ready.criteria_hash.slice(0, 12) });
    await page.locator("#grounding").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${OUT}/demand_live_${w}_project.png` });
    const a = await post("/api/project/archive", { project: got.id, why: "demand_live --lock proof run" }, guest.token);
    const listed = ((await (await fetch(`${BASE}/api/projects?take=100`)).json()).projects || []).map((x) => x.id);
    ok(a.archived && a.archived.by === "buyer" && !listed.includes(got.id), `${w}: the run's project is archived by its buyer, off the public list`, { project: got.id });
  }
  ok(errors.length === 0, `${w}: no page errors`, errors.slice(0, 2));
  await ctx.close();
}
await browser.close();
console.log(fails.length ? `${fails.length} failed` : "all passed");
process.exit(fails.length ? 1 : 0);
