// test_agent_paid_visible, live: three cold loads of the front door (a new browser context each, the cache off) each
// show the newest agent payout, its amount and a link to the transaction on Solana's explorer (devnet), within 10 s of
// the navigation's start. The build writes the line into the page (scripts/live_snapshot.py); the page refreshes it
// from the app after load. The linked transaction is confirmed on devnet with no error.
//
//   node scripts/test_agent_paid_visible.mjs [url]
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const URL = process.argv[2] || "https://drexthealpha.github.io/Knos/";
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_agent_paid_visible.txt`;
const lines = [];
let good = 0, last = null;
const browser = await chromium.launch();
try {
  for (let i = 1; i <= 3; i++) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    const t0 = Date.now();
    await page.goto(URL + `?cold=${Date.now()}`, { waitUntil: "domcontentloaded", timeout: 10000 }).catch(() => null);
    const seen = await page.waitForFunction(() => { const p = document.getElementById("k-paid");
      return p && !p.hidden && p.checkVisibility() && /paid [\d.]+ test units/.test(p.textContent) && p.querySelector('a[href*="explorer.solana.com/tx/"]'); },
      null, { timeout: Math.max(0, 10000 - (Date.now() - t0)) }).then(() => true).catch(() => false);
    const ms = Date.now() - t0;
    const line = ((await page.textContent("#k-paid").catch(() => "")) || "").replace(/\s+/g, " ").trim();
    const href = (await page.getAttribute("#k-paid a", "href").catch(() => "")) || "";
    good += seen;
    last = { line, href };
    lines.push(`${seen ? "ok  " : "FAIL"} cold load ${i}: ${seen ? `shown at ${ms} ms` : "not shown within 10 s"}: ${line || "(no line)"}`);
    await ctx.close();
  }
} finally {
  await browser.close();
}
const sig = (last.href.match(/explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})\?cluster=devnet/) || [])[1];
let status = null;
if (sig) {
  const r = await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignatureStatuses", params: [[sig], { searchTransactionHistory: true }] }) });
  status = ((await r.json()).result || {}).value?.[0] || null;
}
const units = (last.line.match(/paid ([\d.]+) test units/) || [])[1];
const confirmed = !!status && ["confirmed", "finalized"].includes(status.confirmationStatus) && status.err === null;
lines.push(`link: ${last.href || "(none)"}`, `devnet: ${status ? `${status.confirmationStatus}, err ${JSON.stringify(status.err)}, slot ${status.slot}` : "no status"}`);
const ok = good === 3 && confirmed && !!units;
lines.push(ok ? `PASS test_agent_paid_visible: 3 of 3 cold loads showed ${units} test units within 10 s, transaction ${sig.slice(0, 8)}... ${status.confirmationStatus} on devnet (slot ${status.slot})`
              : `FAIL test_agent_paid_visible: ${good} of 3 cold loads showed the line within 10 s${sig ? `, transaction ${confirmed ? "confirmed" : "not confirmed"}` : ", no transaction link"}`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(ok ? 0 : 1);
