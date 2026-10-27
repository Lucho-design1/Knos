// test_qloo_vs_population, live: beside Qloo's launch city, the city population alone would pick among the same
// candidate metros, each with its target by the unchanged D2 formula. The card says "By population: <city>, <T>. By
// Qloo taste: <city>, <T>." for a recorded card with a map, each T recomputing from the report's own metros; How we
// test Knos publishes how often the two differ.
//   node scripts/test_qloo_vs_population.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_qloo_vs_population.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const T = (pop, aff) => Math.max(10, Math.round(pop / 100000 * aff));

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const cards = JSON.parse(readFileSync(REC, "utf8")).cards;
const browser = await chromium.launch();
let both = 0, recompute = 0, checked = 0;
try {
  for (const [w, h] of [[390, 844], [1280, 900]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    for (const [idea, c] of Object.entries(cards)) {
      await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
      await page.fill("#k-q", idea); await page.click("#k-go");
      await page.waitForSelector("#k-card .k-card .k-verdict", { timeout: 60000 }).catch(() => {});
      const line = await page.evaluate(() => { const e = document.querySelector('#k-card .k-card [data-part="by-population"]');
        const t = document.querySelector('#k-card .k-card [data-part="terms"]');
        return e ? { text: e.textContent.trim(), pc: e.dataset.popCity, pt: Number(e.dataset.popTarget), qc: t?.dataset.city, qt: Number(t?.dataset.target) } : null; });
      if (!line) continue;
      const rep = await (await fetch(`${API}/api/report?hash=${c.hash}`)).json();
      const rows = (rep.terms && rep.terms.metros) || [];
      const pop = rows.find((r) => r.city === line.pc), qloo = rows.find((r) => r.city === line.qc);
      const right = !!pop && !!qloo && T(pop.population, pop.affinity) === line.pt && line.qt === rep.terms.target && line.text === `By population: ${line.pc}, ${line.pt}. By Qloo taste: ${line.qc}, ${line.qt}.`;
      both++; recompute += right; checked++;
      lines.push(`${right ? "ok  " : "FAIL"} ${w}px ${idea.slice(0, 34).padEnd(34)} "${line.text}"`);
    }
    await page.close();
  }
  const how = await browser.newPage();
  await how.goto(SITE + "how-we-test.html?t=" + Date.now(), { waitUntil: "load" });
  const pub = await how.evaluate(() => { const e = document.querySelector("#qloo-vs-population [data-count]"); return e ? { n: Number(e.dataset.count), of: Number(e.dataset.of), text: e.textContent.trim(),
    rows: [...document.querySelectorAll("#qloo-vs-population tbody tr")].map((r) => [...r.cells].map((x) => x.textContent)) } : null; });
  ok(!!pub && pub.rows.length === pub.of && pub.rows.filter((r) => r[1] !== r[2]).length === pub.n && pub.rows.every((r) => /, \d+$/.test(r[1]) && /, \d+$/.test(r[2])), `How we test publishes the count: ${pub ? pub.text : "none"}`);
  await how.close();
} finally {
  await browser.close();
}
ok(both > 0 && recompute === checked, `cards showing both columns: ${both} (both widths), each T recomputing: ${recompute} of ${checked}`);
ok(false, "BLOCKED: the count over the D2 run's 15 mapped ideas and the J3 row on /demo/: the D2 run log keeps each idea's top metro only, so their candidate metros need a new heatmap call and Qloo answers 429");
lines.push(`FAIL test_qloo_vs_population: ${fails} check(s) failed`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(1);
