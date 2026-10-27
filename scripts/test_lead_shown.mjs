// test_lead_shown, live: at 390 px the front door's "How it is built" leads with what only Knos has: money held and paid
// on devnet only on proof, GitHub's signature checked inside a Solana program, and the hosted MCP install line. Each is
// visible on scroll, and each link answers 200 or resolves on devnet.
//   node scripts/test_lead_shown.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_lead_shown.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", RPC = "https://api.devnet.solana.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const resolves = async (sig) => {
  for (let i = 0; i < 2; i++) {
    const j = await (await fetch(RPC, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignatureStatuses", params: [[sig], { searchTransactionHistory: true }] }) })).json().catch(() => ({}));
    if (((j.result || {}).value || [])[0]) return true;
    await new Promise((r) => setTimeout(r, 3000));          // one paced retry: the public RPC limits bursts
  }
  return false;
};
const browser = await chromium.launch();
const errors = [];
let links = [];
try {
  const p = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  const want = { held: "Money held and paid on devnet only on proof", oidc: "GitHub's signature checked inside a Solana program", mcp: "The hosted MCP: claude mcp add --transport http knos https://knos.onrender.com/mcp" };
  for (const [k, text] of Object.entries(want)) {
    const li = p.locator(`#k-built [data-lead="${k}"]`);
    await li.scrollIntoViewIfNeeded().catch(() => {});
    const s = await li.evaluate((el) => ({ text: el.textContent.replace(/\s+/g, " ").trim(), on: el.checkVisibility() && el.getBoundingClientRect().top < innerHeight && el.getBoundingClientRect().bottom > 0,
      first: [...el.closest("#k-built").querySelectorAll("li")].indexOf(el), links: [...el.querySelectorAll("a")].map((a) => a.href) })).catch(() => ({ text: "", on: false, first: -1, links: [] }));
    ok(s.on && s.text.startsWith(text) && s.first >= 0 && s.first < 3, `390: "${s.text.slice(0, 110)}" ${s.on ? "visible on scroll" : "not visible"}, row ${s.first + 1} of the section`);
    links = links.concat(s.links.map((u) => [k, u]));
  }
} finally {
  await browser.close();
}
for (const [k, u] of links) {
  const tx = (u.match(/explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})/) || [])[1];
  const good = tx ? await resolves(tx) : (await fetch(u).then((r) => r.status).catch(() => 0)) === 200;
  ok(good, `${k}: ${tx ? `devnet transaction ${tx.slice(0, 10)}... ${good ? "resolves" : "does not resolve"}` : `${u} answers ${good ? 200 : "not 200"}`}`);
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_lead_shown: ${fails} check(s) failed` : `PASS test_lead_shown: the 3 lead lines open How it is built, each visible on scroll at 390 px; ${links.length} links answer 200 or resolve on devnet`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
