// test_qloo_down_honest, local: the app runs in test mode with every Qloo call failing (KNOS_TEST_MODE=1,
// QLOO_FORCE_STATUS=429, no Qloo key), its 8 sample chips' last cards filled with stub answers through the test-mode
// route. Each chip, pressed on the app's own front door, shows the stub card under the exact line "Qloo is not
// answering right now (HTTP 429). Showing the last real answer from <UTC time>."; an idea that is no chip shows "...
// Try again in a few minutes."; no card says "No taste data from Qloo". The repository and the built Pages folder hold
// no Qloo response body, and the app wrote no last card to its state folder. The server is stopped at the end.
//
//   node scripts/test_qloo_down_honest.mjs [built Pages folder]
import { chromium } from "playwright";
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readdirSync, readFileSync, statSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const ROOT = new globalThis.URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_qloo_down_honest.txt`;
const SITE = process.argv[2];
const PORT = 8097, BASE = `http://127.0.0.1:${PORT}`;
const CHIPS = ["an AI recipe planner for families", "a crypto podcast for beginners", "a quantum physics book for kids", "a solar powered music festival",
  "a probiotic kombucha brand", "a recycled ocean plastic swimwear brand", "a tiny home kit for first-time buyers", "10.1038/nature16521"];
const MADE = "2026-10-25T12:00:00Z";
const STALE = "Qloo is not answering right now (HTTP 429). Showing the last real answer from 2026-10-25 12:00 UTC.";
const FRESH = "Qloo is not answering right now (HTTP 429). Try again in a few minutes.";
const lines = [];
let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const stub = (idea, i) => ({ v: 2, kind: "knos-demand-check", idea, label: "LIVE Qloo data (stub for this test)", made: MADE, stage: "full",
  hash: `stub${i}`.padEnd(64, "0"), decision: { verdict: "OPEN", reasons: ["stub answer for the test"] },
  matches: [{ name: `Stub product ${i}`, id: `stub-${i}` }], leader: { name: `Stub product ${i}`, id: `stub-${i}` }, audiences: [{ name: "Stub audience", affinity: 0.9, tied: true }], calls: [] });

const state = mkdtempSync(join(tmpdir(), "knos-f2-"));
const py = join(ROOT, ".venv", "Scripts", "python.exe");
const env = { ...process.env, KNOS_TEST_MODE: "1", QLOO_FORCE_STATUS: "429", HOST: "127.0.0.1", PORT: String(PORT), KNOS_WANTED_STATE: join(state, "state"),
  KNOS_WANTED_CACHE: join(state, "cache"), KNOS_WANTED_RECORD: join(state, "record"), PYTHONPATH: `${join(ROOT, "apps", "wanted")};${join(ROOT, "src")}` };
delete env.QLOO_API_KEY; delete env.KNOS_STATE_ON_CHAIN;
const server = spawn(py, ["-m", "knos_wanted", "serve"], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
let log = "";
server.stdout.on("data", (d) => { log += d; }); server.stderr.on("data", (d) => { log += d; });
const browser = await chromium.launch();
try {
  for (let i = 0; i < 120; i++) {                    // the server's start, once: not a retry of Qloo
    try { if ((await fetch(`${BASE}/healthz`)).ok) break; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  for (const [i, c] of CHIPS.entries()) {
    const r = await fetch(`${BASE}/api/test/record`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: c, card: stub(c, i) }) });
    if (!r.ok) throw new Error(`the test route answered ${r.status}`);
  }
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 120000 });     // the page itself; a slow first start is waited for
  await page.waitForSelector("#k-q", { timeout: 120000 });
  let shown = 0, noTaste = 0;
  const card = async (want) => {      // this press's own card: its stub product, or the no-chip line
    await page.waitForFunction((w) => { const c = document.querySelector("#k-card"); return c?.querySelector("[data-qloo-down]") && c.innerText.includes(w); },
      want, { timeout: 180000 });
    await page.waitForTimeout(400);
    return page.evaluate(() => ({ first: document.querySelector("#k-card .k-card")?.firstElementChild?.textContent.trim(),
      text: document.querySelector("#k-card").innerText, kick: document.querySelector("#k-card .k-kick")?.textContent || "" }));
  };
  for (const [i, c] of CHIPS.entries()) {
    await page.click(`#k-hero .k-chip[data-q="${c}"]`);
    const got = await card(`Stub product ${i}`).catch((e) => ({ first: `(none: ${String(e.message).split("\n")[0].slice(0, 80)})`, text: "", kick: "" }));
    const good = got.first === STALE && got.text.includes(`Stub product ${i}`);
    shown += good; noTaste += got.text.includes("No taste data from Qloo");
    ok(good, `chip ${i + 1} ${c}: ${good ? "the last card under the exact line" : got.first}`);
  }
  await page.fill("#k-q", "a bamboo bicycle for city commuters");
  await page.click("#k-go");
  const fresh = await card("Try again in a few minutes.").catch(() => ({ first: "(none)", text: "" }));
  noTaste += fresh.text.includes("No taste data from Qloo");
  ok(fresh.first === FRESH, `an idea that is no chip: ${fresh.first}`);
  ok(shown === 8, `${shown} of 8 chips show the last card with the exact first line`);
  ok(noTaste === 0, `${noTaste} cards say "No taste data from Qloo"`);
} finally {
  await browser.close();
  // the venv's python.exe is a launcher: its child serves, so the whole tree is stopped
  try { execFileSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { stdio: "ignore" }); } catch { server.kill(); }
  // its files are free before the scan: wait for the process to exit, up to 20 s
  await Promise.race([new Promise((r) => (server.exitCode !== null ? r() : server.once("exit", r))), new Promise((r) => setTimeout(r, 20000))]);
}
// no last card on disk, and no Qloo response body in the repository or the built site
const walk = (d) => readdirSync(d).flatMap((n) => { const f = join(d, n); return statSync(f).isDirectory() ? walk(f) : [f]; });
const readable = (f) => { try { return readFileSync(f, "utf8"); } catch (e) { lines.push(`note ${e.code} reading ${f}`); return ""; } };
const onDisk = existsSync(state) ? walk(state).filter((f) => readable(f).includes("Stub product")).length : 0;
ok(onDisk === 0, `${onDisk} files in the app's state folder hold a last card`);
try { rmSync(state, { recursive: true, force: true }); } catch { /* a file still held: left in the temp folder */ }
const BODY = /"entity_id"\s*:\s*"[0-9A-F-]{36}"[^}]{0,400}"query"\s*:\s*\{\s*"affinity"/;
let listed = "";
try { listed = execFileSync("git", ["grep", "-l", "-E", '"entity_id": ?"[0-9A-F-]{36}"'], { cwd: ROOT, encoding: "utf8" }); } catch { listed = ""; }   // exit 1: no match
const tracked = listed.split("\n").filter(Boolean)
  .filter((f) => BODY.test(readFileSync(join(ROOT, f), "utf8")));
ok(tracked.length === 0, `git grep: ${tracked.length} tracked files hold a Qloo response body ${tracked.slice(0, 3).join(" ")}`);
if (SITE) {
  const inSite = walk(SITE).filter((f) => /\.(html|js|json)$/.test(f) && BODY.test(readFileSync(f, "utf8")));
  ok(inSite.length === 0, `built Pages folder: ${inSite.length} files hold a Qloo response body`);
} else ok(false, "built Pages folder: not given");
lines.push(fails ? `FAIL test_qloo_down_honest: ${fails} check(s) failed` : "PASS test_qloo_down_honest: 8 of 8 chips show the last real card under the exact line, the new idea says try again, 0 \"No taste data\", 0 Qloo bodies in the repo or the site");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
