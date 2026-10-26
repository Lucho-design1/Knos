// test_one_door, live: one front door. GET / on Render answers 301 to the Pages front door and the app lives at /app/
// (its hash routes too); the API, /mcp, /status/qloo and /static/ answer as before; a crawl of every link on the front
// door, /demo/, /check/ and /app/ finds 0 broken; git grep finds no bare link to the Render home (the host with a
// trailing slash or a hash and nothing more; an API base the code adds a path to is not a link).
//   node scripts/test_one_door.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_one_door.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const run = (cmd, args) => { try { return execFileSync(cmd, args, { encoding: "utf8", maxBuffer: 1 << 26 }); } catch (e) { return String(e.stdout || ""); } };
const rpc = async (method, params) => (await (await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) })).json()).result;

const dep = JSON.parse(run("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"]))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const render = run(process.env.KNOS_PY || ".venv/Scripts/python.exe", ["-I", process.env.KNOS_RENDER_LATEST]).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const home = await fetch(API + "/", { redirect: "manual" });
ok(home.status === 301 && home.headers.get("location") === SITE, `GET / on Render: ${home.status} to ${home.headers.get("location")}`);
const bare = await fetch(API + "/app", { redirect: "manual" });
ok(bare.status === 301 && bare.headers.get("location") === "/app/", `GET /app: ${bare.status} to ${bare.headers.get("location")}`);
for (const [path, accept] of [["/app/", "text/html"], ["/api/status", "application/json"], ["/healthz", "*/*"], ["/mcp", "text/html"],
  ["/status/qloo", "text/html"], ["/static/style.css", "text/css"], ["/trace.html", "text/html"]]) {
  const r = await fetch(API + path, { headers: { Accept: accept }, redirect: "manual" });
  ok(r.status === 200, `GET ${path}: ${r.status}`);
}

const PAGES = [SITE, SITE + "demo/", SITE + "check/", API + "/app/"];
const links = new Map();
const browser = await chromium.launch();
try {
  for (const u of PAGES) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto(u + "?t=" + Date.now(), { waitUntil: "load", timeout: 120000 });
    await page.waitForTimeout(1500);
    for (const h of await page.evaluate(() => [...document.querySelectorAll("a[href]")].map((a) => a.href)))
      if (/^https?:/.test(h) && !links.has(h.split("#")[0])) links.set(h.split("#")[0], u);
    await page.close();
  }
  // the app's hash routes, now under /app/
  const page = await browser.newPage();
  await page.goto(API + "/app/#projects", { waitUntil: "load", timeout: 120000 });
  const route = await page.evaluate(() => location.pathname + location.hash);
  ok(route === "/app/#projects", `the app's hash route stays: ${route}`);
  await page.close();
} finally {
  await browser.close();
}
let broken = 0;
for (const [u, from] of links) {
  const tx = /explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})/.exec(u);
  let good, said;
  if (tx) {
    const st = (await rpc("getSignatureStatuses", [[tx[1]], { searchTransactionHistory: true }]))?.value?.[0];
    good = !!st && st.err === null; said = st ? st.confirmationStatus : "not found";
  } else {
    const r = await fetch(u, { redirect: "follow", headers: { "User-Agent": "Mozilla/5.0 (link check)" } }).catch((e) => ({ status: String(e.cause?.code || e) }));
    good = r.status === 200; said = r.status;
  }
  if (!good) { broken++; lines.push(`FAIL ${said} ${u} (on ${from})`); }
}
ok(broken === 0, `link crawl of the front door, /demo/, /check/ and /app/: ${broken} broken of ${links.size}`);
const grep = run("git", ["grep", "-nE", "knos\\.onrender\\.com/(#[A-Za-z]*)?([\"'`)> ]|$)|href=[\"']https://knos\\.onrender\\.com[\"']"]).trim();
const hits = grep ? grep.split("\n") : [];
ok(hits.length === 0, `git grep: ${hits.length} bare links to the Render home${hits.length ? ` (${hits.slice(0, 3).map((h) => h.slice(0, 80)).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_one_door: ${fails} check(s) failed; ${broken} broken of ${links.size} links, ${hits.length} bare home links` :
  `PASS test_one_door: / answers 301 to the front door, app at /app/, 0 broken of ${links.size} links, 0 bare home links`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
