// test_first_screen, live: the front door shows its 4 steps (Check demand, Ready brief, Money held, Paid on proof)
// above the fold at 390 and 1280 px, each with a link (a sample chip, the Ready check, the crossing, ./check/ and the
// newest verdict on devnet); under them one line per built capability, each with its link; every one of those links
// answers 200 or is a confirmed devnet transaction; GET /api/ready answers 200 JSON saying how to POST; the dead
// transaction 3UwN1R... is gone; /check/ shows the devnet transaction of a passed pull request Knos paid for.
//   node scripts/test_first_screen.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SHA = process.argv[2];
const WORLD = process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`;
const OUT = `${WORLD}/test_first_screen.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const PY = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const run = (cmd, args) => { try { return execFileSync(cmd, args, { encoding: "utf8", maxBuffer: 1 << 26 }); } catch (e) { return String(e.stdout || ""); } };
const rpc = async (method, params) => (await (await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) })).json()).result;
const STEPS = ["Check demand", "Ready brief", "Money held", "Paid on proof"];

const dep = JSON.parse(run("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"]))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const render = run(PY, ["-I", process.env.KNOS_RENDER_LATEST]).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const links = new Set();
let caps = 0;
const browser = await chromium.launch();
try {
  for (const [w, h] of [[390, 844], [1280, 800]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await page.waitForTimeout(1000);
    const s = await page.evaluate(() => [...document.querySelectorAll("#k-steps .k-step-list > li")].map((li) => {
      const r = li.getBoundingClientRect();
      return { name: li.querySelector("h3")?.textContent.trim(), bottom: r.bottom, links: [...li.querySelectorAll("a[href]")].map((a) => a.href) }; }));
    const above = s.length === 4 && s.every((x, i) => x.name === STEPS[i] && x.bottom <= h && x.links.length >= 1);
    ok(above, `${w}px: the 4 steps above the fold ${JSON.stringify(s.map((x) => [x.name, Math.round(x.bottom), x.links.length]))}`);
    const by = s.map((x) => x.links);
    ok(by.length === 4 && /\?q=/.test(by[0][0] || "") && /\/api\/ready$/.test(by[1][0] || "") && /\/crossing\/[0-9a-f]{16}\/$/.test(by[2][0] || "")
      && by[3].some((u) => /\/check\/$/.test(u)) && by[3].some((u) => /explorer\.solana\.com\/tx\//.test(u)),
      `${w}px: step links are a sample chip, the Ready check, the crossing, ./check/ and a devnet verdict`);
    await page.screenshot({ path: `${WORLD}/test_first_screen_${w}.png` });
    for (const l of by.flat()) links.add(l);
    const c = await page.evaluate(() => [...document.querySelectorAll("#k-caps > li")].map((li) => [...li.querySelectorAll("a[href]")].map((a) => a.href)));
    caps = c.filter((x) => x.length >= 1).length;
    for (const l of c.flat()) links.add(l);
    const html = await page.content();
    ok(!html.includes("3UwN1R"), `${w}px: the dead transaction 3UwN1R... is not on the page`);
    await page.close();
  }
  ok(caps === 7, `capability rows with a link: ${caps} of 7`);
  // /check/: the devnet transaction of the pull request the newest agent payout paid for, when one names a pull request
  const pay = await (await fetch(API + "/api/agent/payout/latest")).json();
  const pr = /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/.test(String(pay.result || "")) ? pay.result : null;
  if (pr) {
    const page = await browser.newPage();
    await page.goto(SITE + "check/#check=" + encodeURIComponent(pr.replace("https://github.com/", "").replace("/pull/", "/")), { waitUntil: "load" });
    const shown = await page.waitForSelector("#check-tx a", { timeout: 30000 }).then((e) => e.getAttribute("href")).catch(() => "");
    ok(shown === pay.explorer, `/check/ on ${pr}: the devnet transaction ${String(shown).slice(30, 44)}...`);
    await page.close();
  } else {
    lines.push(`ok   /check/: the newest payout names no pull request (${pay.found ? "paid for a project milestone" : "none found"}); nothing to show`);
  }
} finally {
  await browser.close();
}
let bad = 0;
for (const u of links) {
  const tx = /explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})/.exec(u);
  let good;
  if (tx) { const st = (await rpc("getSignatureStatuses", [[tx[1]], { searchTransactionHistory: true }]))?.value?.[0]; good = !!st && st.err === null; }
  else good = (await fetch(u, { redirect: "follow" }).catch(() => ({ status: 0 }))).status === 200;
  if (!good) { bad++; lines.push(`FAIL broken: ${u}`); }
}
ok(bad === 0, `step and capability links: ${links.size - bad} of ${links.size} answer 200 or are confirmed on devnet`);
const r = await fetch(API + "/api/ready");
const j = await r.json().catch(() => ({}));
ok(r.status === 200 && /POST \/api\/ready/.test(j.how || ""), `GET /api/ready: ${r.status} JSON, "${String(j.how || "").slice(0, 40)}"`);
const grep = run("git", ["grep", "-c", "3UwN1R"]).trim();
ok(!grep, `git grep 3UwN1R: ${grep ? grep.split("\n").length : 0} files`);
lines.push(fails ? `FAIL test_first_screen: ${fails} check(s) failed` :
  `PASS test_first_screen: 4 steps above the fold at 390 and 1280, ${caps} capability rows, ${links.size} links good, /api/ready 200`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
