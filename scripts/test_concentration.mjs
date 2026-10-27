// test_concentration, live: every recorded card with a launch city shows, beside each city, Qloo's concentration index
// (0-100), labelled "Qloo concentration index (0-100)" and linked to Qloo's page; each index recomputes from the report's
// heatmap cells (scripts/concentration_check.py). At 390 px and 1280 px.
//   node scripts/test_concentration.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_concentration.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const LINK = "https://qloo.com/use-cases/expand-to-a-new-market";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const doc = JSON.parse(readFileSync(REC, "utf8"));
const ideas = [...Object.keys(doc.cards), "a smart water bottle that glows to remind you to drink"];
const browser = await chromium.launch();
const errors = [];
let withCity = 0, shown = 0;
try {
  for (const [w, scheme] of [[1280, "light"], [390, "dark"]]) {
    const p = await (await browser.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme })).newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    for (const idea of ideas) {
      await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
      await p.fill("#k-q", idea); await p.click("#k-go");
      await p.waitForSelector("#k-card > .k-card .k-verdict", { timeout: 60000 }).catch(() => {});
      await p.waitForTimeout(500);
      const c = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card"), part = k?.querySelector('[data-part="cities"]');
        return { line: !!k?.querySelector('[data-part="terms"]'), hash: k?.querySelector("a[data-receipts]")?.href.match(/receipts\/([0-9a-f]{16})/)?.[1] || "",
          label: part?.querySelector("[data-index-label] a") ? { text: part.querySelector("[data-index-label] a").textContent.trim(), href: part.querySelector("[data-index-label] a").href } : null,
          rows: [...(part?.querySelectorAll(".k-cities li") || [])].map((li) => ({ city: li.querySelector("[data-city]")?.textContent.trim(), index: li.querySelector("[data-index]")?.dataset.index })) }; });
      if (!c.line) { lines.push(`ok   ${w} ${scheme} ${idea.slice(0, 40).padEnd(40)} no launch city: no index`); continue; }
      withCity += w === 1280;
      const rep = await (await fetch(`${API}/api/receipts?id=${c.hash}`)).json().catch(() => null);
      const full = rep && rep.report ? await (await fetch(`${API}/api/report?hash=${rep.report}`)).json() : {};
      const want = JSON.parse(execFileSync(py, [fileURLToPath(new URL("./concentration_check.py", import.meta.url))], { input: JSON.stringify(full), encoding: "utf8" }));
      const same = c.rows.length > 0 && c.rows.every((r) => r.index !== undefined && Number(r.index) === want[r.city]);
      const good = same && c.label && c.label.text === "Qloo concentration index (0-100)" && c.label.href === LINK;
      shown += good && w === 1280;
      ok(good, `${w} ${scheme} ${idea.slice(0, 40).padEnd(40)} ${c.rows.map((r) => `${r.city.split(/[-,]/)[0]} ${r.index}`).join(", ")}; recomputed ${JSON.stringify(Object.fromEntries(Object.entries(want).map(([k, v]) => [k.split(/[-,]/)[0], v])))}`);
    }
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_concentration: ${fails} check(s) failed`
  : `PASS test_concentration: ${shown} of ${withCity} cards with a launch city show Qloo's concentration index for every city, labelled and linked, each recomputing from the heatmap cells, at 390 and 1280`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
