// test_card_truth, live: (a) /app/ says "Qloo: limited" while /status/qloo says limited; (b) "Claude alone" shows only
// when the published table has Claude's answer; (c) How we test's two removal lines give the counts of
// qloo_ablation.json, once; (d) /status/qloo shows "Served from recordings"; (e) Qloo labels are title-cased with no
// "(Lifestyle Preferences ...)"; (f) the crossing's table says held and released, never locked; (g) /demo/ uses the J3
// crossing in all 4 steps.
//   node scripts/test_card_truth.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_card_truth.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const ideas = Object.keys(JSON.parse(readFileSync(REC, "utf8")).cards);
const abl = JSON.parse(readFileSync(fileURLToPath(new URL("../docs/reference/qloo_ablation.json", import.meta.url)), "utf8")).rows;
const moved = (r) => r.city[0] !== r.city[1] || r.target[0] !== r.target[1] || r.label[0] !== r.label[1];
const one = abl.filter((r) => r.removed !== "every Qloo answer"), every = abl.filter((r) => r.removed === "every Qloo answer");
const table = await (await fetch(`${API}/api/qloo-diff`)).json().catch(() => ({ rows: [] }));
const browser = await chromium.launch();
try {
  // (a)
  const q = await (await fetch(`${API}/api/qloo/status?t=${Date.now()}`)).json();
  const app = await browser.newPage();
  await app.goto(`${API}/app/?t=${Date.now()}`, { waitUntil: "load" });
  await app.waitForFunction(() => /Qloo/.test(document.getElementById("modeBadge")?.textContent || ""), null, { timeout: 30000 }).catch(() => {});
  const badge = await app.evaluate(() => document.getElementById("modeBadge")?.textContent.trim() || "");
  ok(badge === (q.limited ? "Qloo: limited" : "Qloo: live"), `(a) /app/ badge "${badge}" while /status/qloo says limited ${q.limited}`);
  await app.close();
  // (b) and (e) on the 6 recorded cards
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  let claudeRight = 0, suffix = 0, lower = [];
  for (const idea of ideas) {
    await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await page.fill("#k-q", idea); await page.click("#k-go");
    await page.waitForSelector("#k-card .k-card .k-verdict", { timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(2500);
    const c = await page.evaluate(() => { const k = document.querySelector("#k-card .k-card");
      const box = k?.parentElement?.querySelector("details[data-claude]") || document.querySelector("#k-card details[data-claude]");
      const labels = [...(k?.querySelectorAll('[data-part="whitespace"] li, [data-part="persona"] li') || [])].map((li) => li.textContent.trim());
      return { shown: !!box && !box.hidden, text: k?.textContent || "", labels }; });
    const has = (table.rows || []).some((x) => x.claude && norm(x.idea) === norm(idea));
    claudeRight += c.shown === has;
    suffix += /\(Lifestyle Preferences/i.test(c.text);
    lower.push(...c.labels.filter((l) => /(^|\s)[a-z]/.test(l.replace(/\s\d.*$/, ""))));
    lines.push(`     ${idea.slice(0, 36).padEnd(36)} Claude alone ${c.shown ? "shown" : "hidden"} (an answer ${has ? "exists" : "does not exist"})`);
  }
  await page.close();
  ok(claudeRight === ideas.length, `(b) "Claude alone" shown exactly when an answer exists: ${claudeRight} of ${ideas.length}`);
  ok(suffix === 0 && lower.length === 0, `(e) labels: ${suffix} cards with a "(Lifestyle Preferences" suffix, ${lower.length} labels not title-cased ${JSON.stringify(lower.slice(0, 3))}`);
  // (c) and (d)
  const how = await browser.newPage();
  await how.goto(SITE + "how-we-test.html?t=" + Date.now(), { waitUntil: "load" });
  const h = await how.evaluate(() => ({ abl: document.querySelector("#ablation [data-one]")?.textContent || "", one: document.querySelector("#ablation [data-one]")?.dataset.one,
    of: document.querySelector("#ablation [data-one]")?.dataset.of, board: [...document.querySelectorAll("#board tbody tr")].find((r) => /signal removed/i.test(r.textContent))?.textContent || "",
    old: /65 removals/.test(document.body.textContent) }));
  const want = `${one.filter(moved).length} of ${one.length}`, wantAll = `${every.filter(moved).length} of ${every.length}`;
  ok(`${h.one} of ${h.of}` === want && h.abl.includes(want) && h.abl.includes(wantAll) && h.board.includes(want) && h.board.includes(wantAll) && !h.old,
    `(c) How we test: both lines say ${want} and ${wantAll}, as qloo_ablation.json counts`);
  await how.close();
  const st = await (await fetch(`${API}/status/qloo?t=${Date.now()}`)).text();
  ok(/<dt>Served from recordings<\/dt><dd>\d+<\/dd>/.test(st), `(d) /status/qloo: "Served from recordings" ${(/<dt>Served from recordings<\/dt><dd>(\d+)/.exec(st) || [])[1]}`);
  // (f)
  const cr = await (await fetch(`${SITE}crossing/7b4ed16b8c2903dc/?t=${Date.now()}`)).text();
  const tbl = cr.slice(cr.indexOf("<th>#</th>"));
  ok(!/locked/i.test(cr) && /<th>Held<\/th>/.test(tbl) && /<th>Released<\/th>/.test(tbl), `(f) the crossing's table says held and released, ${(cr.match(/locked/gi) || []).length} "locked"`);
  // (g)
  const facts = JSON.parse(readFileSync(fileURLToPath(new URL("../web/crossing/7b4ed16b8c2903dc/facts.json", import.meta.url)), "utf8"));
  const sigs = new Set(facts.orders.flatMap((o) => [o.lock, o.release]));
  const demo = await browser.newPage();
  await demo.goto(SITE + "demo/?t=" + Date.now(), { waitUntil: "load" });
  const steps = await demo.evaluate(() => ["step-demand", "step-brief", "step-held", "step-paid"].map((id) => ({ id, text: document.getElementById(id)?.textContent || "",
    links: [...(document.getElementById(id)?.querySelectorAll("a[href]") || [])].map((a) => a.href) })));
  await demo.close();
  const j3 = (s) => s.links.some((u) => u.includes("/crossing/7b4ed16b8c2903dc/") || [...sigs].some((g) => u.includes(g)));
  ok(steps.every(j3) && /graphene-coated cycling jacket/i.test(steps[0].text), `(g) /demo/: ${steps.filter(j3).length} of 4 steps use the J3 crossing (step 1: "${steps[0].text.trim().slice(0, 60)}")`);
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_card_truth: ${fails} check(s) failed` : "PASS test_card_truth: (a) to (g) true live");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
