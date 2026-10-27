// test_own_idea, live: a judge's own idea. The hosted MCP knos_demand_check gives the verdict REST /api/check gives, for
// the 6 recorded chips and the 10 typed test ideas of the nearest-answer test. 5 new typed ideas, written here, get 5
// different closest matches or the no-match text; no card presents another idea's answer as the typed one; the first
// screen carries no quota banner at 390 px and 1280 px.
//   node scripts/test_own_idea.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, appendFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_own_idea.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const P1 = ["a glow in the dark water bottle for hikers", "a quantum physics podcast for teens", "a recycled plastic sneaker for runners",
  "an encrypted email app for journalists", "a solar powered phone charger for festivals", "a meal planner app for busy parents",
  "a crypto savings app for students", "a smart watch that tracks hydration", "a bamboo cutting board brand", "a vintage vinyl record shop"];
const NEW = ["a sleep mask for night shift nurses", "a board game cafe for families", "an electric cargo bike rental in Chicago",
  "a podcast about urban gardening", "a vegan protein bar for marathon runners"];
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
if (process.env.KNOS_RENDER_LATEST) {
  const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
  const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
  ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);
}
const post = async (p, b) => (await fetch(API + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).json();
const mcp = async (name, args) => { const j = await post("/mcp", { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } });
  return j.result?.structuredContent || JSON.parse(j.result?.content?.[0]?.text || "{}"); };
// 1. MCP and REST agree
const chips = Object.keys(JSON.parse(readFileSync(REC, "utf8")).cards);
let same = 0;
for (const idea of [...chips, ...P1]) {
  const [r, m] = await Promise.all([post("/api/check", { idea }), mcp("knos_demand_check", { idea })]);
  const agree = (r.decision || {}).verdict === (m.decision || {}).verdict && r.hash === m.report;
  same += agree;
  lines.push(`${agree ? "ok  " : "FAIL"} ${idea.slice(0, 44).padEnd(44)} REST ${(r.decision || {}).verdict} ${String(r.hash).slice(0, 12)} | MCP ${(m.decision || {}).verdict} ${String(m.report).slice(0, 12)}`);
  if (!agree) fails++;
}
ok(same === chips.length + P1.length, `MCP and REST give the same verdict and report: ${same} of ${chips.length + P1.length}`);
// 2. 5 new ideas, typed on the front door
const browser = await chromium.launch();
const errors = [];
const matches = [];
let posing = 0;
try {
  for (const [w, scheme] of [[390, "dark"], [1280, "light"]]) {
    const p = await (await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: scheme })).newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await p.waitForSelector("#k-card > .k-card", { timeout: 60000 }).catch(() => {});
    const screen = await p.evaluate(() => { const b = document.querySelector("[data-qloo-limit]"), H = innerHeight;
      const shown = [...document.querySelectorAll("body *")].filter((e) => e.children.length === 0 && e.checkVisibility() && e.getBoundingClientRect().top < H)
        .map((e) => e.textContent).join(" ");
      return { banner: !!b && !b.hidden && b.textContent.trim().length > 0, words: /calls left|monthly limit|0 of 50,000/i.test(shown) }; });
    ok(!screen.banner && !screen.words, `${w} ${scheme}: the first screen shows ${screen.banner || screen.words ? "a quota banner" : "no quota banner"}`);
    if (w !== 1280) continue;
    for (const idea of NEW) {
      await p.fill("#k-q", idea); await p.click("#k-go");
      await p.waitForFunction((i) => { const k = document.querySelector("#k-card > .k-card"); return k && !k.closest(".k-past") && (k.querySelector("[data-qloo-down]") || k.matches("[data-nearest-options]") || k.querySelector(".k-kick")?.textContent.includes(i)); }, idea, { timeout: 30000 }).catch(() => {});
      await p.waitForTimeout(400);
      const c = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card");
        return { kick: k?.querySelector(".k-kick")?.textContent.trim() || "", first: k?.querySelector("[data-qloo-down]")?.textContent.trim() || "",
          none: k?.matches("[data-nearest-options]") ? k.querySelector(".k-verdict")?.textContent.trim() : "", opts: [...(k?.querySelectorAll("[data-q]") || [])].map((b) => b.dataset.q) }; });
      const other = c.kick && !c.kick.toLowerCase().includes(idea.toLowerCase());
      const said = !other || c.first.startsWith("Qloo has not answered your exact idea yet. Closest idea it has answered:") || c.none;
      posing += !said;
      const m = (c.first.match(/Closest idea it has answered: (.+), answered \d{4}-\d{2}-\d{2}\.$/) || [])[1] || null;
      matches.push(c.none ? "none" : m);
      ok(said && (m || c.none.startsWith("Qloo has not answered an idea close to this yet.")), `${idea}: ${m ? `closest "${m}"` : c.none ? `"${c.none}" ${c.opts.length} option(s)` : `"${c.first || c.kick}"`}`);
    }
  }
} finally {
  await browser.close();
}
const found = matches.filter((m) => m && m !== "none");
ok(found.length === new Set(found).size && matches.length === 5 && matches.every(Boolean), `5 new ideas: ${found.length} closest matches, all different (${new Set(found).size}); ${matches.filter((m) => m === "none").length} with the no-match text`);
ok(posing === 0, `cards presenting another idea's answer as the typed one: ${posing}`);
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_own_idea: ${fails} check(s) failed`
  : `PASS test_own_idea: MCP and REST agree on ${same} of ${chips.length + P1.length}; 5 new ideas got ${new Set(found).size} different closest matches and ${matches.filter((m) => m === "none").length} no-match texts; 0 cards pose as the typed idea; no quota banner at 390 or 1280`);
console.log(lines.join("\n"));
appendFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
