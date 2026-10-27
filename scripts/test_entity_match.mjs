// test_entity_match: the match rule (apps/wanted check.entity_tied: a shared Qloo tag with the idea's tags, or the
// idea's category word named) scored on 20 hand-labelled pairs from the recordings (a private fixture), then live:
// the AI recipe planner's card shows neither Secret Recipe nor Lee's Famous Recipe Chicken, and every recorded card
// still renders.
//   node scripts/test_entity_match.mjs <commit sha under test> <private recordings file> <private fixture>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC, FIX] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_entity_match.txt`;
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const SITE = "https://drexthealpha.github.io/Knos/";
const PY = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const render = execFileSync(PY, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

// the rule on the recordings, as the server applies it at load (check.retie after check.scrub)
const scored = JSON.parse(execFileSync(PY, ["-I", "-c", `import json,sys; sys.path[:0]=['apps/wanted','src']
from knos_wanted import check
cards=json.load(open(sys.argv[1],encoding='utf-8'))['cards']; fx=json.load(open(sys.argv[2],encoding='utf-8'))['pairs']
kept={k: {m.get('name') for m in check.retie(check.scrub(c)).get('matches') or []} for k,c in cards.items()}
print(json.dumps([{**p, 'got': 'match' if p['entity'] in kept.get(p['idea'], set()) else 'not'} for p in fx]))`, REC, FIX], { encoding: "utf8", cwd: ROOT }));
const right = scored.filter((p) => p.got === p.label).length;
for (const p of scored) lines.push(`${p.got === p.label ? "ok  " : "miss"} ${p.idea.slice(0, 34).padEnd(34)} ${p.entity.slice(0, 40).padEnd(40)} label ${p.label}, rule ${p.got}`);
ok(scored.length === 20 && right >= 18, `the rule on 20 hand labels: ${right} of ${scored.length} right`);

const ideas = Object.keys(JSON.parse(readFileSync(REC, "utf8")).cards);
const browser = await chromium.launch();
let rendered = 0;
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  for (const idea of ideas) {
    await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await page.fill("#k-q", idea); await page.click("#k-go");
    const got = await page.waitForSelector("#k-card .k-card .k-verdict", { timeout: 60000 }).then(() => true).catch(() => false);
    const text = got ? await page.evaluate(() => document.querySelector("#k-card .k-card").textContent) : "";
    rendered += got;
    if (/recipe planner/.test(idea)) ok(!/Secret Recipe|Lee's Famous Recipe Chicken/.test(text), `the AI recipe planner's card names neither Secret Recipe nor Lee's Famous Recipe Chicken`);
  }
} finally {
  await browser.close();
}
ok(rendered === ideas.length, `recorded cards that render: ${rendered} of ${ideas.length}`);
lines.push(fails ? `FAIL test_entity_match: ${fails} check(s) failed` : `PASS test_entity_match: ${right} of 20 labels right, the recipe planner's wrong matches gone, ${rendered} of ${ideas.length} cards render`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
