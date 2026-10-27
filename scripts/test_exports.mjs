// test_exports, live: on each of the 6 recorded results' /r/<id> pages, the three downloads work: "Download brief (PDF)"
// (a one-page PDF holding the idea), "Download calls (CSV)" (one row per Qloo call, with endpoint, parameters without any
// key, ms, cached and the part fed; 0 response bodies) and "Download Ready brief (JSON)".
//   node scripts/test_exports.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_exports.txt`;
const API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const cards = JSON.parse(readFileSync(REC, "utf8")).cards;
const browser = await chromium.launch();
const errors = [];
let all = 0, bodies = 0;
try {
  const p = await (await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } })).newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  for (const [idea, c] of Object.entries(cards)) {
    const id = c.hash.slice(0, 16);
    await p.goto(`${API}/r/${id}?t=${Date.now()}`, { waitUntil: "load" });
    const got = {};
    for (const [kind, text] of [["pdf", "Download brief (PDF)"], ["csv", "Download calls (CSV)"], ["json", "Download Ready brief (JSON)"]]) {
      const [d] = await Promise.all([p.waitForEvent("download", { timeout: 30000 }).catch(() => null), p.click(`[data-exports] a:text-is("${text}")`).catch(() => null)]);
      const path = d ? await d.path().catch(() => null) : null;
      got[kind] = path ? readFileSync(path) : null;
    }
    const pdf = got.pdf ? got.pdf.toString("latin1") : "", csvText = got.csv ? got.csv.toString("utf8") : "";
    let json = null; try { json = JSON.parse(got.json ? got.json.toString("utf8") : ""); } catch { json = null; }
    const rows = csvText.trim().split("\n");
    // response bodies: every digest and excerpt the recorded calls hold, none of which may be in the CSV
    const digests = (c.calls || []).flatMap((x) => [x.body_digest, x.out]).filter((s) => typeof s === "string" && s.length >= 12);
    const leaked = digests.filter((s) => csvText.includes(s)).length;
    bodies += leaked;
    const good = pdf.startsWith("%PDF-") && /%%EOF\s*$/.test(pdf) && pdf.includes("Knos.") && rows[0] === "n,endpoint,params,ms,cached,fed"
      && rows.length - 1 === (c.calls || []).length && leaked === 0 && !/key=/i.test(csvText) && json && typeof json.ready === "boolean" && json.report === c.hash;
    all += good;
    lines.push(`${good ? "ok  " : "FAIL"} ${idea.slice(0, 40).padEnd(40)} PDF ${got.pdf ? got.pdf.length : 0} bytes; CSV ${rows.length - 1} rows of ${(c.calls || []).length} calls, ${leaked} bodies; JSON ready ${json ? json.ready : "?"}${json && json.criteria_hash ? `, criteria ${json.criteria_hash.slice(0, 12)}` : ""}`);
    if (!good) fails++;
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_exports: ${all} of ${Object.keys(cards).length} results; ${fails} check(s) failed`
  : `PASS test_exports: all 3 downloads work on ${all} of ${Object.keys(cards).length} recorded results; the CSVs hold ${bodies} response bodies`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
