// test_live_log, live: the front door's /calls/ lists the server's last Qloo requests (at least 50 rows from the recordings
// and live traffic, newest first, no response body, no key); a run's card says "Qloo calls: N live, M cached, T ms"; on two
// chips the matched product is asked about first ("Is this what you mean?"): Yes runs the check, No shows the next 3 matches.
//   node scripts/test_live_log.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_live_log.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
// the log as JSON: only the six fields and where the row came from; no body, no key
const j = await (await fetch(`${API}/api/calls`)).json();
const rows = j.calls || [];
const KEYS = new Set(["at", "call", "params", "status", "ms", "cached", "origin"]);
const bodies = rows.filter((r) => Object.keys(r).some((k) => !KEYS.has(k)) || JSON.stringify(r.params || {}).match(/"[^"]*(key|token|secret)[^"]*":/i)).length;
const order = rows.every((r, i) => i === 0 || String(rows[i - 1].at) >= String(r.at) || rows[i - 1].origin !== r.origin);
ok(rows.length >= 50 && bodies === 0, `/api/calls: ${rows.length} rows (${rows.filter((r) => r.origin === "recorded").length} recorded, ${rows.filter((r) => r.origin !== "recorded").length} live), ${bodies} with a body or a key`);
ok(order, "newest first");
const browser = await chromium.launch();
const errors = [];
try {
  // the page
  const p = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(`${SITE}calls/?t=${Date.now()}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await p.waitForFunction(() => document.querySelectorAll("#c-rows tr[data-origin]").length > 0, null, { timeout: 30000 }).catch(() => {});
  const page = await p.evaluate(() => ({ rows: document.querySelectorAll("#c-rows tr[data-origin]").length, h1: document.querySelector("h1")?.textContent,
    cols: [...document.querySelectorAll("thead th")].map((x) => x.textContent), wide: document.documentElement.scrollWidth }));
  ok(page.rows >= 50 && page.cols.join("|") === "Time (UTC)|Endpoint|Parameters|Status|ms|Cached" && page.wide <= 390,
    `/calls/ at 390: ${page.rows} rows under ${page.cols.join(", ")}; page ${page.wide} px wide`);
  // the confirm step on two chips
  const f = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  f.on("pageerror", (e) => errors.push(e.message));
  await f.goto(`${SITE}?t=${Date.now()}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  const confirm = async (chip) => {
    await f.click(`[data-q="${chip}"]`);
    await f.waitForSelector("#k-card [data-confirm]", { timeout: 30000 }).catch(() => {});
    return f.evaluate(() => document.querySelector("#k-card [data-confirm] .k-verdict")?.textContent.trim() || "");
  };
  const asked1 = await confirm("a solar powered music festival");
  await f.click("#k-card [data-sure]").catch(() => {});
  await f.waitForFunction(() => document.querySelector("#k-card > .k-card [data-part=calls-head]"), null, { timeout: 45000 }).catch(() => {});
  const head = await f.evaluate(() => ({ head: document.querySelector("#k-card > .k-card [data-part=calls-head]")?.textContent.trim() || "",
    kick: document.querySelector("#k-card > .k-card .k-kick")?.textContent.trim() || "" }));
  ok(/^Is this what you mean\? .+/.test(asked1) && /solar powered music festival/i.test(head.kick), `solar festival: "${asked1}", Yes ran the check (${head.kick.slice(0, 50)})`);
  ok(/^Qloo calls: \d+ live, \d+ cached, [\d,]+ ms$/.test(head.head), `the run's header: "${head.head}"`);
  const asked2 = await confirm("a probiotic kombucha brand");
  await f.click("#k-card [data-other]").catch(() => {});
  await f.waitForSelector("#k-card [data-confirm-next]", { timeout: 10000 }).catch(() => {});
  const next = await f.evaluate(() => [...document.querySelectorAll("#k-card [data-confirm-next] [data-pick]")].map((b) => b.textContent.trim()));
  ok(/^Is this what you mean\? .+/.test(asked2) && next.length === 3, `kombucha: "${asked2}", No showed ${next.length} next matches (${next.join(" | ")})`);
} catch (e) {
  ok(false, `the browser step stopped: ${String(e.message).split("\n")[0].slice(0, 160)}`);
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 2).join("; ").slice(0, 200)})` : ""}`);
lines.push(fails ? `FAIL test_live_log: ${fails} check(s) failed`
  : `PASS test_live_log: /calls/ shows ${rows.length} requests with 0 bodies; the run header counts live, cached and ms; the confirm step works on 2 chips`);
console.log(lines.join("\n"));
appendFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
