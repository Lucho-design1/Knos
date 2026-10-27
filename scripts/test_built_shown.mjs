// test_built_shown: (a) knos_zk's devnet runs are a fixture its test reads (passes, not skipped) and git grep finds no
// "not deployed" for knos_zk; (b) live, every recorded card says what each Qloo signal changes on it and marks every
// calls row "decides" or "context"; (c) the cache test proves a 2xx answer older than 7 days is served.
//   node scripts/test_built_shown.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_built_shown.txt`;
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const PY = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const SITE = "https://drexthealpha.github.io/Knos/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const run = (cmd, args, cwd = ROOT) => { try { return { out: execFileSync(cmd, args, { encoding: "utf8", cwd, env: { ...process.env, KNOS_FULL_TEST_OUTPUT: "1" } }), code: 0 }; }
  catch (e) { return { out: String(e.stdout || "") + String(e.stderr || ""), code: e.status || 1 }; } };

const dep = JSON.parse(run("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"]).out)[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const render = run(PY, ["-I", process.env.KNOS_RENDER_LATEST]).out.trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);
// (a)
const zk = run(PY, ["-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", "tests/test_zk_client.py::test_devnet_receipt_is_public_and_consistent"]);
ok(zk.code === 0 && /1 passed/.test(zk.out) && !/skipped/.test(zk.out), `(a) knos_zk's devnet fixture test: ${(zk.out.trim().split("\n").at(-1) || "").trim()}`);
const g = run("git", ["grep", "-n", "-i", "not deployed"]).out.split("\n").filter((l) => /zk|5M67Aqw1/i.test(l));
ok(g.length === 0, `(a) git grep "not deployed" for knos_zk: ${g.length}${g.length ? ` ${JSON.stringify(g.slice(0, 2))}` : ""}`);
// (c)
const cache = run(PY, ["-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_qloo_rest.py::test_cache_hit_and_ttl"], ROOT + "apps/wanted");
ok(cache.code === 0 && /1 passed/.test(cache.out), `(c) a 2xx answer 40 days old is served from the cache: ${(cache.out.trim().split("\n").at(-1) || "").trim()}`);
// (b)
const ideas = Object.keys(JSON.parse(readFileSync(REC, "utf8")).cards);
const browser = await chromium.launch();
let rows = 0, marked = 0, withLine = 0;
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  for (const idea of ideas) {
    await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await page.fill("#k-q", idea); await page.click("#k-go");
    await page.waitForSelector('#k-card .k-card [data-part="calls"] li', { timeout: 60000 }).catch(() => {});
    const c = await page.evaluate(() => { const k = document.querySelector("#k-card .k-card");
      const rs = [...(k?.querySelectorAll('[data-part="calls"] li') || [])];
      return { line: k?.querySelector('[data-part="signals"]')?.textContent.trim() || "", rows: rs.length,
        marked: rs.filter((li) => ["decides", "context"].includes(li.querySelector("[data-role]")?.dataset.role)).length,
        decides: rs.filter((li) => li.querySelector('[data-role="decides"]')).length }; });
    rows += c.rows; marked += c.marked; withLine += /^What each Qloo signal changes here: /.test(c.line);
    lines.push(`${c.rows && c.marked === c.rows && c.line ? "ok  " : "FAIL"} ${idea.slice(0, 36).padEnd(36)} ${c.marked} of ${c.rows} rows marked (${c.decides} decides); "${c.line.slice(0, 90)}"`);
  }
} finally {
  await browser.close();
}
ok(rows > 0 && marked === rows && withLine === ideas.length, `(b) ${withLine} of ${ideas.length} cards say what each signal changes; ${marked} of ${rows} calls rows marked decides or context`);
lines.push(fails ? `FAIL test_built_shown: ${fails} check(s) failed` : `PASS test_built_shown: the knos_zk fixture test passes, 0 "not deployed", ${marked} of ${rows} rows marked, the 40-day cache entry served`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
