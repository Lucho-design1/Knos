// test_quota_honest, live: every sub-item of N3 in one script. While /api/qloo/status says month_left 0: the banner and
// every limited answer (the card, REST /api/check, knos_demand_check, `knos demand`) say "Qloo's monthly limit for this
// demo is reached until <reset date>. Cards show the last live answers.", never "few minutes"; an undecided card shows no
// Share and no launch button; /api/status says mode "limited". /api/taste/movie answers 503 JSON with the reason; GET /mcp
// answers 200 with a discovery document; knos_usage shows no goal; knos_ready's benchmark is its overall numbers only;
// knos_research_card names no product when its phrase is the generic one; no public answer and no server source says
// "CHAMPION".
//   node scripts/test_quota_honest.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_quota_honest.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const getj = async (p) => { const r = await fetch(API + p); return { status: r.status, type: r.headers.get("content-type") || "", body: await r.json().catch(() => null) }; };
const post = async (p, b) => (await fetch(API + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).json();
const mcp = async (name, args) => { const j = await post("/mcp", { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } });
  return j.result?.structuredContent || JSON.parse(j.result?.content?.[0]?.text || "{}"); };
const BAD = "closest existing products: Qloo's rate limit";

// the server meets Qloo's month once (a check it refuses without sending), so its limit headers are read
await post("/api/check", { idea: "a refillable shampoo bar subscription", stage: "verdict" }).catch(() => null);
const q = (await getj("/api/qloo/status")).body || {};
const day = q.month_reset ? new Date(q.month_reset).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "";
const LINE = `Qloo's monthly limit for this demo is reached until ${day}. Cards show the last live answers.`;
ok(String(q.month_left) === "0", `/api/qloo/status: month_left ${q.month_left} of ${q.month_limit}, resets ${q.month_reset}`);
ok(q.line === LINE, `/api/qloo/status line: "${q.line}"`);
const st = (await getj("/api/status")).body || {};
ok(st.mode === "limited", `/api/status mode "${st.mode}"`);
// REST /api/check: the line on the answer, one plain reason, no rate-limit fragment
const rest = await post("/api/check", { idea: "a cold brew coffee shop", place: "Austin", leader: "Starbucks" });
const restText = JSON.stringify(rest);
ok(rest.qloo_limit === LINE && !restText.includes(BAD) && !/few minutes/i.test(restText), `REST /api/check: "${rest.qloo_limit}"`);
// knos_demand_check: its reason is the one sentence
const dc = await mcp("knos_demand_check", { idea: "a cold brew coffee shop", place: "Austin" });
const reasons = dc.decision?.reasons || [];
ok(reasons.length === 1 && reasons[0] === LINE && !JSON.stringify(dc).includes(BAD), `knos_demand_check reasons: ${JSON.stringify(reasons)}`);
// `knos demand`, the repository's CLI
let cli = "";
try { cli = execFileSync(fileURLToPath(new URL("../.venv/Scripts/knos.exe", import.meta.url)), ["demand", "a cold brew coffee shop", "--place", "Austin"], { encoding: "utf8", cwd: ROOT, timeout: 120000 }); } catch (e) { cli = String(e.stdout || e.message); }
ok(cli.includes(LINE) && !cli.includes(BAD) && !/few minutes/i.test(cli), `knos demand: ${cli.includes(LINE) ? "the line" : cli.slice(0, 160).replace(/\s+/g, " ")}`);
// the front door: the banner, a typed idea's card, no Share or launch button on an undecided card
const browser = await chromium.launch();
const errors = [];
try {
  for (const [w, scheme] of [[390, "dark"], [1280, "light"]]) {
    const cx = await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: scheme });
    const p = await cx.newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await p.waitForFunction(() => { const b = document.querySelector("[data-qloo-limit]"); return b && !b.hidden && b.textContent.trim(); }, null, { timeout: 30000 }).catch(() => {});
    const banner = await p.evaluate(() => document.querySelector("[data-qloo-limit]")?.textContent.trim() || "");
    ok(banner === LINE, `${w} ${scheme}: the banner says "${banner}"`);
    for (const idea of ["a vintage vinyl record shop", "a crypto savings app for students"]) {
      await p.fill("#k-q", idea); await p.click("#k-go");
      await p.waitForSelector("#k-card > .k-card", { timeout: 30000 }).catch(() => {});
      await p.waitForTimeout(500);
      const c = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card");
        return { text: k?.textContent || "", undecided: !!k?.matches('[data-verdict="CANNOT_DECIDE"], [data-nearest-options]'), share: !!k?.querySelector("[data-share]"), cta: !!k?.querySelector(".k-cta"),
          line: [...(k?.querySelectorAll("[data-qloo-down], [data-qloo-limit-line]") || [])].map((x) => x.textContent.trim()) }; });
      const said = c.undecided || c.line.includes(LINE);
      ok(said && !/few minutes/i.test(c.text) && (!c.undecided || (!c.share && !c.cta)),
        `${w} ${scheme}: "${idea}": ${c.undecided ? `undecided, Share ${c.share ? "shown" : "hidden"}, launch ${c.cta ? "shown" : "hidden"}` : `lines ${JSON.stringify(c.line)}`}`);
    }
    await cx.close();
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
// /api/taste/movie
const tm = await getj("/api/taste/movie?title=Inception&year=2010");
ok(tm.status === 503 && tm.type.includes("json") && tm.body && tm.body.error, `/api/taste/movie: ${tm.status} "${tm.body && tm.body.error}"`);
// GET /mcp
const dm = await getj("/mcp");
ok(dm.status === 200 && dm.body && dm.body.name === "knos" && dm.body.transport === "streamable-http" && dm.body.protocolVersion && dm.body.tools_list?.url === `${API}/mcp`,
  `GET /mcp: ${dm.status} ${JSON.stringify(dm.body && { name: dm.body.name, transport: dm.body.transport, protocolVersion: dm.body.protocolVersion, post: dm.body.tools_list?.url })}`);
// knos_usage, knos_ready, knos_research_card
const us = await mcp("knos_usage", {});
ok(!("goals" in us) && !JSON.stringify(us).includes("CHAMPION"), `knos_usage: keys ${Object.keys(us).join(", ")}`);
const brief = { title: "A check", milestones: [{ name: "Tests pass", target: "pytest exits 0 on the repo", verifier: { check: "pytest" }, deadline_days: 3 }] };
const rd = await mcp("knos_ready", { brief });
const bench = rd.idt?.benchmark || {};
ok(JSON.stringify(Object.keys(bench).sort()) === JSON.stringify(["overall_ratio", "raw", "ready_pass_rate", "tasks", "vague_pass_rate"]), `knos_ready benchmark: ${JSON.stringify(bench)}`);
const rc = await mcp("knos_research_card", { ref: "10.1038/s41586-021-03819-2" });
ok(rc.product === null && rc.product_line === "Name the product this result enables", `knos_research_card (AlphaFold): product ${JSON.stringify(rc.product)}, "${rc.product_line}"`);
// no "CHAMPION" in a public answer, nor in the server's source
const tl = await post("/mcp", { jsonrpc: "2.0", id: 1, method: "tools/list" });
const answers = [JSON.stringify(us), JSON.stringify(st), JSON.stringify(q), JSON.stringify(tl), JSON.stringify((await getj("/api/usage")).body), JSON.stringify((await getj("/openapi.json")).body)];
const grep = execFileSync("git", ["-C", ROOT, "grep", "-c", "CHAMPION", "--", "apps/wanted/knos_wanted", "src/knos"], { encoding: "utf8" }).trim();
ok(!answers.some((a) => a.includes("CHAMPION")) && grep === "", `"CHAMPION": ${answers.filter((a) => a.includes("CHAMPION")).length} public answers, git grep in the server's source ${grep || "0"}`);
lines.push(fails ? `FAIL test_quota_honest: ${fails} check(s) failed`
  : `PASS test_quota_honest: month_left 0 said as "${LINE}" on the banner, the cards, REST, MCP and the CLI, never "few minutes"; /api/status limited; taste 503 JSON; GET /mcp 200; 0 goals, 0 task rows, 0 "CHAMPION"`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
