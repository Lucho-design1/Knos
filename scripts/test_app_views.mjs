// test_app_views, live: the app's views. /app/#buy, #fund and #make each list the released crossing 7b4ed16b8c2903dc
// (or are absent from the navigation), and #buy stays under /app/. #agents' search for "kombucha" returns at least one
// result. #research shows its verdict first, the log folded under Details. GET /api/projects?take=10 and knos_projects
// answer cold in under 3 s and under 50 KB. Then 5 fresh loads of /app/#projects, each after 15 minutes with no request
// for the projects list, show the list in under 5 s and never "HTTP 502".
//   node scripts/test_app_views.mjs <commit sha under test> [--idle-minutes 15]
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2), SHA = args[0];
const IDLE = Number(args[args.indexOf("--idle-minutes") + 1] || 15) * 60000;
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_app_views.txt`;
const APP = "https://knos.onrender.com";
const lines = []; let fails = 0;
const say = (l) => { lines.push(l); console.log(l); writeFileSync(OUT, l + "\n", { flag: "a" }); };
const ok = (c, what) => { say(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const latest = () => execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
const render = latest();
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const browser = await chromium.launch();
const errors = [];
try {
  // the cold list: the first request for it since the deploy
  const t0 = Date.now(), r = await fetch(`${APP}/api/projects?take=10&t=${t0}`), body = await r.text(), ms = Date.now() - t0;
  ok(r.status === 200 && ms < 3000 && body.length < 50000 && JSON.parse(body).projects.length >= 1, `GET /api/projects?take=10, cold: ${r.status} in ${ms} ms, ${body.length.toLocaleString("en-US")} bytes`);
  const t1 = Date.now();
  const mc = await (await fetch(`${APP}/mcp`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "knos_projects", arguments: { take: 10 } } }) })).text();
  const mt = Date.now() - t1, res = (JSON.parse(mc).result || {}), got = res.structuredContent || JSON.parse(res.content?.[0]?.text || "{}");
  ok(mt < 3000 && mc.length < 60000 && got.shape === "summary" && (got.projects || []).length >= 1, `knos_projects take 10: ${mt} ms, ${mc.length.toLocaleString("en-US")} bytes, ${(got.projects || []).length} summaries`);
  const cx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const p = await cx.newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  for (const v of ["buy", "fund", "make"]) {
    await p.goto(`${APP}/app/?t=${Date.now()}#${v}`, { waitUntil: "load" });
    await p.waitForSelector(`#v-${v} [data-crossing="7b4ed16b8c2903dc"]`, { timeout: 20000 }).catch(() => {});
    const s = await p.evaluate((v) => ({ url: location.pathname + location.hash, item: document.querySelector(`#v-${v} [data-crossing="7b4ed16b8c2903dc"]`)?.textContent.replace(/\s+/g, " ").trim() || "",
      inNav: !!document.querySelector(`nav.roles a[data-view="${v}"]`), shown: !!document.querySelector(`#v-${v}`)?.checkVisibility() }), v);
    ok((s.item && s.shown) || !s.inNav, `/app/#${v}: ${s.url}; ${s.item ? `"${s.item.slice(0, 110)}"` : s.inNav ? "empty" : "absent from the navigation"}`);
    if (v === "buy") ok(s.url.startsWith("/app/"), `#buy stays under /app/ (${s.url})`);
  }
  await p.goto(`${APP}/app/?t=${Date.now()}#agents`, { waitUntil: "load" });
  const box = p.locator("#v-agents input").first();
  await box.waitFor({ timeout: 20000 }).catch(() => {});
  await box.fill("kombucha"); await box.press("Enter");
  await p.waitForTimeout(4000);
  const found = await p.evaluate(() => { const o = document.querySelector("#v-agents"); return { rows: [...o.querySelectorAll("p.small")].filter((x) => /kombucha/i.test(x.textContent)).map((x) => x.textContent.trim()), said: o.textContent.includes("every gate armed") }; });
  ok(found.rows.length >= 1 && !found.said, `#agents search "kombucha": ${found.rows.length} result(s): ${found.rows.slice(0, 2).join(" | ").slice(0, 160)}`);
  // #research: the sample paper, run as a reader would; the verdict comes first and the log is folded under Details
  await p.goto(`${APP}/app/?t=${Date.now()}#research`, { waitUntil: "load" });
  await p.click('#v-research [data-ref="10.1038/nature16521"]').catch(() => {});
  await p.click("#crossBtn").catch(() => {});
  await p.waitForFunction(() => document.querySelector("#outcome")?.textContent.trim(), null, { timeout: 120000 }).catch(() => {});
  const rs = await p.evaluate(() => { const o = document.querySelector("#outcome"), d = document.querySelector("#stepsBox");
    return { verdict: o?.querySelector("h3")?.textContent.trim() || "", first: !!(o && d && (o.compareDocumentPosition(d) & Node.DOCUMENT_POSITION_FOLLOWING)),
      folded: !!d && !d.open && d.querySelector("summary")?.textContent.trim() === "Details", steps: d?.querySelectorAll("li").length || 0 }; });
  ok(rs.verdict && rs.first && rs.folded, `#research: verdict "${rs.verdict}" first; the log (${rs.steps} steps) folded under Details: ${rs.folded}`);
  await cx.close();
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
// 5 fresh loads, each after the idle, no request for the projects list in between
let good = 0;
for (let i = 1; i <= 5; i++) {
  await new Promise((r) => setTimeout(r, IDLE));
  const b = await chromium.launch();
  try {
    const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
    const t0 = Date.now();
    await p.goto(`${APP}/app/?t=${t0}#projects`, { waitUntil: "domcontentloaded" });
    const shown = await p.waitForFunction(() => { const l = document.querySelector("#projList"); return l && l.children.length > 0 && l.checkVisibility(); }, null, { timeout: 5000, polling: 50 }).then(() => true, () => false);
    const ms = Date.now() - t0;
    await p.waitForTimeout(1000);
    const text = await p.evaluate(() => document.body.innerText);
    const n = await p.evaluate(() => document.querySelectorAll("#projList > li").length);
    const r = latest();
    const fine = shown && ms < 5000 && !/HTTP 502/.test(text);
    good += fine;
    ok(fine, `load ${i} after ${IDLE / 60000} idle minutes: the list (${n} projects) in ${ms} ms; "HTTP 502" ${/HTTP 502/.test(text) ? "shown" : "absent"}; Render ${r[1]} ${r[2]}`);
  } finally {
    await b.close();
  }
}
say(fails ? `FAIL test_app_views: ${fails} check(s) failed` : `PASS test_app_views: #buy, #fund and #make each list the released crossing, #buy under /app/, "kombucha" found, the verdict first in #research, /api/projects cold under 3 s and 50 KB, and ${good} of 5 idle loads under 5 s with no "HTTP 502"`);
process.exit(fails ? 1 : 0);
