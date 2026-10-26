// test_docs_audit, live: the docs audit applied. Its named tests pass (test_public_is_for_users, test_docs_map,
// test_docs_plain, test_diagrams, test_pypi_readme); git grep finds none of the retired words in the public files; a
// crawl of the front door, the app and the README's links finds 0 broken; the README's 2 diagrams render on GitHub.
//   node scripts/test_docs_audit.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_docs_audit.txt`;
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const PY = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const SITE = "https://drexthealpha.github.io/Knos/", APP = "https://knos.onrender.com/app/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const run = (cmd, args, env = {}) => { try { return { out: execFileSync(cmd, args, { encoding: "utf8", cwd: ROOT, maxBuffer: 1 << 26, env: { ...process.env, ...env } }), code: 0 }; }
  catch (e) { return { out: String(e.stdout || "") + String(e.stderr || ""), code: e.status || 1 }; } };
const rpc = async (sig) => (await (await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignatureStatuses", params: [[sig], { searchTransactionHistory: true }] }) })).json()).result?.value?.[0];

const dep = JSON.parse(run("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"]).out)[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const t = run(PY, ["-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_docs_map.py", "tests/test_docs_plain.py", "tests/test_diagrams.py", "tests/test_pypi_readme.py"],
  { KNOS_FULL_TEST_OUTPUT: "1", PATH: `${process.env.KNOS_SHIM || ""};${process.env.PATH}` });
ok(t.code === 0, `test_docs_map, test_docs_plain, test_diagrams, test_pypi_readme: ${(t.out.trim().split("\n").at(-1) || "").trim()}`);
const pub = run(PY, ["-I", "scripts/test_public_is_for_users.py"]);
ok(pub.code === 0, `test_public_is_for_users: ${(pub.out.trim().split("\n").at(-1) || "").slice(0, 120)}`);
for (const w of ["founder decision", "DECISIONS.md", "TASK-ALPENGLOW", "Algora", "Upwork", "Bountysource", "hackathon"]) {
  const g = run("git", ["grep", "-il", w, "--", "README*", "docs", "web", "apps/wanted/knos_wanted/static", "config"]).out.trim();
  const files = g ? g.split("\n") : [];
  ok(files.length === 0, `git grep "${w}": ${files.length} files${files.length ? ` (${files.join(", ")})` : ""}`);
}
// the README's links, the front door's and the app's
const readme = run("git", ["show", `${SHA}:README.md`]).out;
const links = new Map();
for (const m of readme.matchAll(/\]\((https?:[^)\s]+)\)/g)) links.set(m[1].split("#")[0], "README");
for (const m of readme.matchAll(/\]\(([^)\s:#]+)(#[^)\s]*)?\)/g)) links.set(`https://github.com/drexthealpha/Knos/blob/main/${m[1].replace(/^\.\//, "")}`, "README");
const browser = await chromium.launch();
try {
  for (const u of [SITE, APP]) {
    const p = await browser.newPage();
    await p.goto(u + "?t=" + Date.now(), { waitUntil: "load", timeout: 90000 });
    await p.waitForTimeout(1500);
    for (const h of await p.evaluate(() => [...document.querySelectorAll("a[href]")].map((a) => a.href))) if (/^https?:/.test(h)) links.set(h.split("#")[0].split("?t=")[0], u);
    await p.close();
  }
  // the README's two diagrams on GitHub's rendered page
  const gh = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await gh.goto(`https://github.com/drexthealpha/Knos/blob/${SHA}/README.md`, { waitUntil: "load", timeout: 90000 });
  await gh.waitForTimeout(3000);
  const pics = await gh.evaluate(() => [...document.querySelectorAll("article img, .markdown-body img")].filter((i) => /diagrams\/readme-\d\.svg/.test(i.getAttribute("src") || i.dataset.canonicalSrc || "") || /readme-\d\.svg/.test(i.src))
    .map((i) => ({ src: i.src.slice(-40), loaded: i.complete && i.naturalWidth > 0 })));
  ok(pics.length === 2 && pics.every((x) => x.loaded), `the README's diagrams render on GitHub: ${JSON.stringify(pics)}`);
  await gh.close();
} finally {
  await browser.close();
}
let bad = 0;
for (const [u, from] of links) {
  const tx = /explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})/.exec(u);
  let good;
  if (tx) { const st = await rpc(tx[1]).catch(() => null); good = !!st && st.err === null; }
  else good = (await fetch(u, { redirect: "follow", headers: { "User-Agent": "Mozilla/5.0 (link check)" } }).catch(() => ({ status: 0 }))).status === 200;
  if (!good) { bad++; lines.push(`FAIL broken: ${u} (from ${from})`); }
}
ok(bad === 0, `link crawl of the front door, the app and the README: ${bad} broken of ${links.size}`);
lines.push(fails ? `FAIL test_docs_audit: ${fails} check(s) failed` : `PASS test_docs_audit: named tests pass, 0 retired words, 0 broken of ${links.size} links, 2 README diagrams render`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
