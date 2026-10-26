// test_qloo_honest, live: /status/qloo, in the app's stylesheet, shows today's calls, the last success, the last 429 and
// the cache hit rate; the front door's line above the chips agrees with it (shown exactly while Qloo limits requests);
// every calls row on the 6 recorded chips shows its milliseconds or "recorded <date>", with K1(d)'s five fields.
//   node scripts/test_qloo_honest.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_qloo_honest.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const ideas = Object.keys(JSON.parse(readFileSync(REC, "utf8")).cards);
const browser = await chromium.launch();
let rows = 0, good = 0;
try {
  const st = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const resp = await st.goto(`${API}/status/qloo?t=${Date.now()}`, { waitUntil: "load" });
  const s = await st.evaluate(() => ({ font: getComputedStyle(document.body).fontFamily, facts: [...document.querySelectorAll("dt")].map((d) => [d.textContent, d.nextElementSibling?.textContent]),
    limited: document.querySelector("[data-limited]")?.textContent || "" }));
  const need = ["Calls sent today", "Answered from the cache", "Last success", "Last 429"];
  ok(resp.status() === 200 && !/times/i.test(s.font) && need.every((n) => s.facts.some(([k]) => k === n)),
    `/status/qloo ${resp.status()}, font ${s.font.slice(0, 24)}: ${s.facts.map(([k, v]) => `${k} ${v}`).join("; ")}`);
  await st.close();
  const d = await (await fetch(`${API}/api/qloo/status?t=${Date.now()}`)).json();
  const land = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await land.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  await land.waitForTimeout(4000);
  const banner = await land.evaluate(() => { const e = document.querySelector("[data-qloo-limit]"); if (!e) return null;
    const chips = document.querySelector(".k-try"); return { text: e.textContent.trim(), href: e.querySelector("a")?.href || "", above: !!(chips && e.compareDocumentPosition(chips) & Node.DOCUMENT_POSITION_FOLLOWING) }; });
  const agree = d.limited ? !!banner && banner.text === d.line && banner.above && banner.href.startsWith(`${API}/status/qloo`) && s.limited === d.line : !banner;
  ok(agree, `the front door agrees with /status/qloo: limited ${d.limited}, line "${d.line || ""}", banner ${banner ? `"${banner.text}"` : "none"}`);
  await land.close();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  for (const idea of ideas) {
    await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await page.fill("#k-q", idea); await page.click("#k-go");
    await page.waitForSelector('#k-card .k-card [data-without][aria-pressed="false"]', { timeout: 60000 }).catch(() => {});
    const rs = await page.evaluate(() => [...document.querySelectorAll('#k-card .k-card [data-part="calls"] li')].map((li) => li.textContent.replace(/\s+/g, " ").trim()));
    // "#n GET /path params · <ms> ms | recorded <date> · cached|live · the part it set"
    const fine = rs.filter((r) => /^#\d+ (GET|POST) \/\S+ \S.* · (\d+ ms|recorded \d{4}-\d{2}-\d{2}) · (cached|live)( · failed)? · \S/.test(r)).length;
    rows += rs.length; good += fine;
    lines.push(`${fine === rs.length && rs.length ? "ok  " : "FAIL"} ${idea.slice(0, 40).padEnd(40)} ${fine} of ${rs.length} rows with ms or recorded <date> and the five fields`);
  }
  ok(rows > 0 && good === rows, `calls rows on ${ideas.length} recorded chips: ${good} of ${rows}`);
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_qloo_honest: ${fails} check(s) failed` : `PASS test_qloo_honest: /status/qloo styled with its 4 facts, the front door agrees, ${good} of ${rows} calls rows with ms or recorded <date>`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
