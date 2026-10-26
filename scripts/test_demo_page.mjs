// test_demo_page, live: /demo/ on the front door (Pages at the commit under test) shows its 4 numbered steps on one
// screen at 390 and 1280 px; every link answers 200 or is a confirmed devnet transaction; the front door's
// "See it in 3 clicks" links it; Lighthouse (mobile) gives performance and accessibility at least 0.90.
//   node scripts/test_demo_page.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync, readFileSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_demo_page.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", DEMO = SITE + "demo/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const gh = (p) => JSON.parse(execFileSync("gh", ["api", p], { encoding: "utf8" }));
const rpc = async (method, params) => (await (await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) })).json()).result;

const dep = gh("repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1")[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const browser = await chromium.launch();
const exe = chromium.executablePath();
let links = [];
try {
  for (const [w, h] of [[390, 844], [1280, 800]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(DEMO + "?t=" + Date.now(), { waitUntil: "load" });
    const s = await page.evaluate(() => [...document.querySelectorAll(".steps > li")].map((li) => {
      const r = li.getBoundingClientRect(); return { n: li.id, top: r.top, bottom: r.bottom, links: li.querySelectorAll("a").length }; }));
    ok(s.length === 4 && s.every((x) => x.bottom <= innerHeightOf(h) && x.links >= 1), `${w}px: 4 numbered steps on one screen, each with a link ${JSON.stringify(s.map((x) => [x.n, Math.round(x.bottom)]))}`);
    links = await page.evaluate(() => [...document.querySelectorAll("a[href]")].map((a) => a.href));
    await page.close();
  }
  const home = await browser.newPage();
  await home.goto(SITE + "?t=" + Date.now(), { waitUntil: "domcontentloaded" });
  const strip = await home.evaluate(() => document.querySelector("#k-clicks a")?.href || "");
  ok(strip === DEMO, `the front door's "See it in 3 clicks" links ${strip}`);
  await home.close();
} finally {
  await browser.close();
}
function innerHeightOf(h) { return h; }
for (const u of [...new Set(links)]) {
  const tx = /explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})/.exec(u);
  if (tx) {
    const st = (await rpc("getSignatureStatuses", [[tx[1]], { searchTransactionHistory: true }]))?.value?.[0];
    ok(st && st.err === null && ["confirmed", "finalized"].includes(st.confirmationStatus), `transaction ${tx[1].slice(0, 10)}... ${st && st.confirmationStatus}`);
  } else {
    const r = await fetch(u, { redirect: "follow" });
    ok(r.status === 200, `${r.status} ${u}`);
  }
}
const dir = mkdtempSync(join(tmpdir(), "lh-"));
execFileSync("npx", ["--yes", "lighthouse@12.2.1", DEMO, "--only-categories=performance,accessibility", "--output=json", `--output-path=${join(dir, "r.json")}`,
  "--quiet", "--chrome-flags=--headless=new --no-sandbox"], { env: { ...process.env, CHROME_PATH: exe }, stdio: "ignore", shell: true, timeout: 300000 });
const lh = JSON.parse(readFileSync(join(dir, "r.json"), "utf8")).categories;
ok(lh.performance.score >= 0.9 && lh.accessibility.score >= 0.9, `Lighthouse (mobile) on /demo/: performance ${lh.performance.score}, accessibility ${lh.accessibility.score}`);
lines.push(fails ? `FAIL test_demo_page: ${fails} check(s) failed` :
  `PASS test_demo_page: 4 steps on one screen at 390 and 1280, ${new Set(links).size} links good, Lighthouse ${lh.performance.score} / ${lh.accessibility.score}`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
