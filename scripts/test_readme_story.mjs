// test_readme_story: README diagram 1's demand and record steps say what the spec asks; test_diagrams, test_readme_plain
// and test_pypi_readme pass; and GitHub's page for the repository shows both README diagrams drawn (each Mermaid frame,
// given up to 30 s, holds a drawn SVG).
//   node scripts/test_readme_story.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_readme_story.txt`;
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const head = execFileSync("git", ["-C", ROOT, "ls-remote", "origin", "refs/heads/main"], { encoding: "utf8" }).split(/\s/)[0];
ok(head === SHA, `main on GitHub at ${head.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const readme = readFileSync(`${ROOT}/README.md`, "utf8");
ok(readme.includes('demand["Demand check on Qloo: who wants it, the launch city and the pre-order target"]')
  && readme.includes('record["Each payment and refund is kept in the Knos record in Sibyl, anchored on Solana"]'), "README diagram 1: the demand step and the record step");
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const t = spawnSync(py, ["-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_diagrams.py", "tests/test_readme_plain.py", "tests/test_pypi_readme.py"], { cwd: ROOT, encoding: "utf8" });
ok(t.status === 0, `test_diagrams, test_readme_plain, test_pypi_readme: ${(t.stdout || "").trim().split("\n").pop()}`);
const browser = await chromium.launch();
try {
  const p = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await p.goto("https://github.com/drexthealpha/Knos?t=" + Date.now(), { waitUntil: "load" });
  const t0 = Date.now();
  let drawn = 0, frames = 0;
  while (Date.now() - t0 < 30000) {
    const fs = p.frames().filter((f) => /viewscreen|render\.githubusercontent|mermaid/.test(f.url()));
    frames = fs.length;
    drawn = 0;
    for (const f of fs) drawn += await f.evaluate(() => { const s = document.querySelector("svg"); return !!s && s.getBoundingClientRect().height > 20 && s.querySelectorAll("g").length > 3; }).catch(() => false);
    if (drawn >= 2) break;
    await p.waitForTimeout(1000);
  }
  ok(drawn >= 2, `GitHub draws the README's diagrams: ${drawn} of ${frames} Mermaid frames hold a drawn SVG after ${Math.round((Date.now() - t0) / 1000)} s`);
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_readme_story: ${fails} check(s) failed` : "PASS test_readme_story: diagram 1 says the launch city and target and the Knos record in Sibyl anchored on Solana; the 3 tests pass; GitHub draws both diagrams");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
