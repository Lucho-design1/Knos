// test_usage_counter, live: the front door's counter (demand checks run, Ready briefs made, devnet transactions of the
// knos_pay program), as the page shows it after the reader's first move, equals at one moment the app's store
// (GET /api/usage reads the stored counts on every call) and this test's own count of the program's signatures on
// devnet (getSignaturesForAddress, 1,000 a page).
//
//   node scripts/test_usage_counter.mjs
import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";

const FRONT = "https://drexthealpha.github.io/Knos/", APP = "https://knos.onrender.com";
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_usage_counter.txt`;
const PROGRAM = JSON.parse(readFileSync(new globalThis.URL("../src/knos/settle/v2/program_ids.json", import.meta.url), "utf8")).knos_pay;
const rpc = async (method, params) => (await (await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) })).json()).result;
async function chainCount() {
  let n = 0, before;
  for (;;) {
    const page = await rpc("getSignaturesForAddress", [PROGRAM, { limit: 1000, commitment: "confirmed", ...(before ? { before } : {}) }]) || [];
    n += page.length;
    if (page.length < 1000) return n;
    before = page[page.length - 1].signature;
  }
}
const lines = [];
const browser = await chromium.launch();
let shown = null;
try {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await page.goto(FRONT + `?t=${Date.now()}`, { waitUntil: "load" });
  await page.mouse.move(200, 200);
  await page.mouse.wheel(0, 400);
  await page.waitForSelector("#k-usage[data-live]", { timeout: 90000 }).catch(() => null);
  shown = await page.evaluate(() => { const u = document.getElementById("k-usage"); if (!u || u.hidden) return null;
    const n = (k) => Number(u.querySelector(`[data-n="${k}"]`)?.textContent);
    return { checks: n("checks"), briefs: n("briefs"), payouts: n("payouts"), live: u.dataset.live === "1", text: u.textContent.replace(/\s+/g, " ").trim() }; });
} finally {
  await browser.close();
}
const [store, chain] = await Promise.all([fetch(`${APP}/api/usage`).then((r) => r.json()), chainCount()]);
lines.push(`page:  ${shown ? shown.text : "(no counter)"}`, `store: ${store.checks} checks, ${store.briefs} briefs since ${store.since}`, `chain: ${chain} signatures of knos_pay ${PROGRAM} on devnet`);
const ok = !!shown && shown.live && shown.checks === store.checks && shown.briefs === store.briefs && shown.payouts === chain;
lines.push(ok ? `PASS test_usage_counter: page = store = chain at one moment: ${shown.checks} checks, ${shown.briefs} briefs, ${shown.payouts} devnet transactions`
              : `FAIL test_usage_counter: ${!shown ? "no counter on the front door" : `page ${shown.checks}/${shown.briefs}/${shown.payouts} vs store ${store.checks}/${store.briefs} and chain ${chain}`}`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(ok ? 0 : 1);
