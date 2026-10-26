// test_quality_page, live: /quality/ answers 200 and shows, for the commit under test, every Lighthouse score (phone and
// desktop, four categories, five pages) and axe in light and dark on the same five pages with 0 violations.
//   node scripts/test_quality_page.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_quality_page.txt`;
const Q = "https://drexthealpha.github.io/Knos/quality/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const res = await fetch(Q + "?t=" + Date.now());
ok(res.status === 200, `/quality/ answers ${res.status}`);
const q = await (await fetch(Q + "quality.json?t=" + Date.now())).json().catch(() => null);
ok(q && q.commit === SHA, `quality.json is for ${q ? String(q.commit).slice(0, 7) : "none"}, measured ${q && q.at}`);
const lh = (q && q.lighthouse) || [], axe = (q && q.axe) || [];
const scored = lh.filter((r) => r.scores && ["performance", "accessibility", "best-practices", "seo"].every((c) => typeof r.scores[c] === "number"));
ok(lh.length === 10 && scored.length === 10, `Lighthouse: ${scored.length} of 10 page and device runs scored in all four categories`);
for (const r of lh) lines.push(`     ${r.page} ${r.form}: ${r.error ? `not measured (${r.error})` : JSON.stringify(r.scores)}`);
const measured = axe.filter((r) => typeof r.violations === "number"), viol = measured.reduce((a, r) => a + r.violations, 0);
ok(axe.length === 10 && measured.length === 10 && viol === 0, `axe: ${measured.length} of 10 page and theme runs, ${viol} violations ${JSON.stringify(measured.filter((r) => r.violations).map((r) => [r.page, r.scheme, r.ids.map((x) => x.id)]))}`);
// the page draws every number it holds
const browser = await chromium.launch();
try {
  const p = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = []; p.on("pageerror", (e) => errors.push(String(e.message)));
  await p.goto(Q + "?t=" + Date.now(), { waitUntil: "load" });
  await p.waitForSelector("#q-lh tbody tr", { timeout: 20000 }).catch(() => {});
  const shown = await p.evaluate(() => ({ lh: document.querySelectorAll("#q-lh tbody tr").length, axe: document.querySelectorAll("#q-axe tbody tr").length,
    commit: document.querySelector("#q-for code")?.textContent || "" }));
  ok(shown.lh === lh.length && shown.axe === axe.length && SHA.startsWith(shown.commit) && errors.length === 0,
    `/quality/ draws ${shown.lh} Lighthouse rows and ${shown.axe} axe rows for ${shown.commit}, ${errors.length} page errors`);
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_quality_page: ${fails} check(s) failed` : `PASS test_quality_page: /quality/ 200, 10 of 10 Lighthouse runs and 10 of 10 axe runs for ${SHA.slice(0, 7)}, 0 axe violations`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
