// test_leftovers, live and on the commit under test: each fix from the code and design reviews, checked where it shows.
//   node scripts/test_leftovers.mjs <commit sha under test>
// KNOS_RENDER_LATEST (optional): a script printing Render's newest deploy as "<id> <status> <sha>".
import { chromium } from "playwright";
import { execFileSync, spawnSync } from "node:child_process";
import { appendFileSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_leftovers.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com", FRONT = "https://drexthealpha.github.io";
const PY = process.env.KNOS_PY || `${ROOT}.venv/Scripts/python.exe`;
const lines = []; let fails = 0, n = 0;
const ok = (c, what) => { n++; lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const at = (path) => execFileSync("git", ["-C", ROOT, "show", `${SHA}:${path}`], { encoding: "utf8", maxBuffer: 1 << 26 });
const post = async (p, b) => (await fetch(API + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).json();
const mcp = async (name, args) => { const j = await post("/mcp", { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } });
  return j.result?.structuredContent || JSON.parse(j.result?.content?.[0]?.text || "{}"); };
const timed = async (url) => { const t = performance.now(); const r = await fetch(url); await r.arrayBuffer(); return [r.status, Math.round(performance.now() - t)]; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
if (process.env.KNOS_RENDER_LATEST) {
  const render = execFileSync(PY, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
  ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);
}

// 1. the first screen's CSS: app.css and tokens.css as the front door links them, under 65,000 bytes; docs/perf.json says so
const front = await (await fetch(`${SITE}?t=${Date.now()}`)).text();
const sheets = [...front.matchAll(/<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"/g)].map((m) => new URL(m[1], SITE).href).filter((u) => u.startsWith(SITE));
let css = 0;
for (const u of sheets) css += (await (await fetch(u)).arrayBuffer()).byteLength;
const perf = JSON.parse(at("docs/perf.json")).first_screen_bytes;
ok(css > 0 && css < 65000 && !sheets.some((u) => u.includes("card.css")), `first-screen CSS on the front door: ${css} bytes in ${sheets.length} sheets (under 65,000; card.css not among them)`);
ok(perf.css < 65000 && perf.budget.css === 65000, `docs/perf.json: ${perf.css} bytes of CSS, budget ${perf.budget.css}`);
for (const u of [`${SITE}brand/card.css`, `${API}/static/brand/card.css`]) {
  const card = await fetch(u);
  ok(card.ok && (await card.text()).includes(".k-card-head"), `${u}: ${card.status}, the card's rules on their own`);
}

// 2. tests/web/check.mjs on this commit: the UTC wording and the devnet read
const check = spawnSync("node", [`${ROOT}tests/web/check.mjs`], { encoding: "utf8", cwd: ROOT, timeout: 600000 });
const fl = (check.stdout || "").split("\n").filter((l) => /^FAIL/.test(l));
ok(check.status === 0 && fl.length === 0, `tests/web/check.mjs: exit ${check.status}, ${fl.length} failing line(s)${fl.length ? ` (${fl.slice(0, 2).join("; ").slice(0, 200)})` : ""}`);

// 3 and 4. the kombucha card: the word the card shows and the receipt's verdict agree; the receipt answers the front door
const browser = await chromium.launch();
let kombucha = null;
const errors = [];
try {
  const p = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "domcontentloaded", timeout: 90000 });
  await p.fill("#k-q", "a probiotic kombucha brand"); await p.click("#k-go");
  await p.waitForFunction(() => { const k = document.querySelector("#k-card > .k-card"); return k && !k.closest(".k-past") && /kombucha/i.test(k.textContent); }, null, { timeout: 45000 }).catch(() => {});
  await p.waitForTimeout(600);
  const word = await p.evaluate(() => document.querySelector("#k-card > .k-card .k-verdict")?.textContent.trim() || "");
  const r = await post("/api/check", { idea: "a probiotic kombucha brand" });
  kombucha = String(r.hash || "").slice(0, 16);
  const res = await fetch(`${API}/api/receipts?id=${kombucha}`, { headers: { Origin: FRONT } });
  const rc = res.ok ? await res.json() : {};
  ok(res.headers.get("access-control-allow-origin") === FRONT, `/api/receipts answers the front door: allow-origin ${res.headers.get("access-control-allow-origin")}`);
  const same = /^Open/.test(word) ? rc.verdict === "OPEN" : /^Not yet/.test(word) ? rc.verdict === "REFUSE" : rc.verdict !== "OPEN";
  ok(word && same, `kombucha: the card says "${word.slice(0, 60)}", the receipt says ${rc.verdict}`);
  // 5. /with-without at 390: no sideways scroll
  const w = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();
  await w.goto(`${API}/with-without?t=${Date.now()}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await w.waitForTimeout(1500);
  const wide = await w.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
  ok(wide[0] <= wide[1], `/with-without at 390: page ${wide[0]} px wide in a ${wide[1]} px window`);
  // 6. the brief panel: every benchmark field valley.js reads is in /api/ready's answer, and the panel draws with no error
  const valley = await (await fetch(`${API}/valley.js?t=${Date.now()}`)).text();
  const used = [...new Set([...valley.matchAll(/t\.benchmark\.([a-z_]+)/g)].map((m) => m[1]))];
  const ready = await post("/api/ready", { brief: { goal: "Ship a CSV export for the projects list", done: "pytest tests/test_export.py passes", budget: "20 USDC", deadline: "2026-11-30" } });
  const bench = (ready.idt || {}).benchmark || {};
  ok(used.length > 0 && used.every((k) => k in bench), `valley.js reads ${used.length} benchmark fields, all in /api/ready (${used.filter((k) => !(k in bench)).join(", ") || "none missing"})`);
  const a = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const appErr = [];
  a.on("pageerror", (e) => appErr.push(e.message));
  await a.goto(`${API}/app/?all=1&t=${Date.now()}#projects`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await a.waitForTimeout(2500);
  ok(appErr.length === 0, `/app/#projects: ${appErr.length} page error(s)${appErr.length ? ` (${appErr[0].slice(0, 120)})` : ""}`);
} catch (e) {
  ok(false, `the browser step stopped: ${String(e.message).split("\n")[0].slice(0, 160)}`);
} finally {
  await browser.close();
}
ok(errors.length === 0, `front door page errors: ${errors.length}`);

// 7. the projects list: the first answer after this deploy and the next both under 2 s; the keepalive asks for /app/
const [s1, t1] = await timed(`${API}/api/projects?take=10`), [s2, t2] = await timed(`${API}/api/projects?take=10`);
ok(s1 === 200 && t1 < 2000 && s2 === 200 && t2 < 2000, `/api/projects?take=10: ${t1} ms, then ${t2} ms (under 2,000)`);
const v = at("apps/wanted/knos_wanted/valley.py"), keep = at(".github/workflows/keepalive.yml");
ok(!v.includes('glob("projects-summary-*.json")') && v.includes("def warm_summaries") && at("apps/wanted/knos_wanted/server.py").includes("valley.warm_summaries"),
  "the summary is built at boot and only rebuilt after a save; no save deletes its file");
ok(/knos\.onrender\.com\/app\//.test(keep) && /\/ 5 % 2/.test(keep), "keepalive.yml asks for /app/ every other 5-minute run (10 minutes)");

// 8. the PDF wraps words: a long idea through exports.pdf, and the kombucha brief as served
const wrap = spawnSync(PY, ["-I", "-c", [
  "import sys, re; sys.path[:0] = ['src', 'apps/wanted']",
  "from knos_wanted import exports",
  "idea = ' '.join(['an extraordinarily well-documented community seed library'] * 6)",
  "b = exports.pdf({'idea': idea, 'decision': {'verdict': 'REFUSE'}}, 'https://knos.onrender.com/r/0123456789abcdef').decode('latin-1')",
  "parts = re.findall(r'\\((.*?)\\) Tj', b)",
  "print(int(('Knos. ' + idea) in ' '.join(parts)), max(len(p) for p in parts))"].join("\n")], { encoding: "utf8", cwd: ROOT });
const [whole, longest] = (wrap.stdout || "0 0").trim().split(/\s+/).map(Number);
ok(whole === 1 && longest <= 90, `exports.pdf: a 360-character idea reads whole when its lines are joined by spaces (${whole ? "yes" : "no"}), longest line ${longest}`);
if (kombucha) {
  const pdf = Buffer.from(await (await fetch(`${API}/r/${kombucha}.pdf`)).arrayBuffer()).toString("latin1");
  const parts = [...pdf.matchAll(/\((.*?)\) Tj/g)].map((m) => m[1]);
  ok(parts.length > 3 && parts.every((x) => x.length <= 90) && parts.join(" ").includes("Knos. a probiotic kombucha brand"),
    `the kombucha brief PDF: ${parts.length} lines, each at most 90 characters, the idea whole`);
}

// 9. the memory search finds what the front door shows
const mem = await mcp("knos_memory_search", { q: "kombucha" });
ok((mem.rows || []).length > 0, `MCP knos_memory_search "kombucha": ${(mem.rows || []).length} row(s): ${String(mem.said || "").slice(0, 80)}`);

// 10. the npm statement(): a page size and a time limit, said in its notes when the read is cut short
const sdk = await import(new URL("../sdk/settle/agent.js", import.meta.url).href);
const t0 = performance.now();
const st = await sdk.statement("https://api.devnet.solana.com", "142920951", "2026-10", { timeoutMs: 1, pageSize: 5 }).catch((e) => ({ error: e.message }));
ok(!st.error && st.escrow && st.escrow.complete === false && st.notes.some((x) => /time limit/.test(x)),
  `statement() with a 1 ms time limit and 5 a page: ${st.error ? st.error.slice(0, 120) : `cut short and said so (${Math.round(performance.now() - t0)} ms)`}`);

// 11. the Qloo cache, said as qloo_rest.py does it, with the day cap and the month floor
const safe = await (await fetch(`${API}/qloo-safe-use?t=${Date.now()}`)).text(), dc = at("docs/reference/DEMAND_CHECK.md");
for (const [name, text] of [["/qloo-safe-use", safe], ["DEMAND_CHECK.md", dc]])
  ok(/no time limit/.test(text) && !/for 7\s+days/.test(text) && /1,500/.test(text) && /2,000/.test(text), `${name}: "no time limit", the 1,500 day cap and the 2,000 month floor; no 7 days`);

// 12. PRICING: the diagram draws the page's table, and its picture is of that text
const pr = at("docs/PRICING.md"), block = pr.split("```mermaid")[1].split("```")[0];
ok(/Demand check: free/.test(block) && /Ready brief/.test(block) && /1%/.test(block) && !/pull request|Meter/i.test(block), "docs/PRICING.md's diagram: the demand check, the Ready brief, the 1% release; no pull request, no meter");
const dg = spawnSync(PY, ["-I", "scripts/diagrams.py", "--check"], { encoding: "utf8", cwd: ROOT });
ok(dg.status === 0, `scripts/diagrams.py --check: ${(dg.stdout || dg.stderr).trim().split("\n").at(-1)}`);

// 13. scripts/test_dev_surfaces.py: a venv's own folder on any system, Render read only when told how
const dev = at("scripts/test_dev_surfaces.py");
ok(/"Scripts" if os\.name == "nt" else "bin"/.test(dev) && /os\.environ\.get\("KNOS_RENDER_LATEST"\)/.test(dev), "scripts/test_dev_surfaces.py: portable venv paths, KNOS_RENDER_LATEST optional");

lines.push(fails ? `FAIL test_leftovers: ${fails} of ${n} checks failed` : `PASS test_leftovers: ${n} of ${n} checks; first-screen CSS ${css} bytes; projects list ${t1} ms then ${t2} ms`);
console.log(lines.join("\n"));
appendFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
