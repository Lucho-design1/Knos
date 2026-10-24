// test_agent_paid_visible, live: the front door shows the newest payout to an agent, its amount and a link to the
// transaction on Solana's explorer (devnet), and that transaction is confirmed on devnet with no error.
//
//   node scripts/test_agent_paid_visible.mjs [url]
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const URL = process.argv[2] || "https://drexthealpha.github.io/Knos/";
const OUT = process.env.KNOS_WORLD ? `${process.env.KNOS_WORLD}/test_agent_paid_visible.txt` : "C:/Users/zulab/knos-v1-private/v0328/world/test_agent_paid_visible.txt";
const lines = [];
const browser = await chromium.launch();
let line = "", href = "";
try {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await page.goto(URL, { waitUntil: "load" });
  await page.waitForSelector("#k-paid:not([hidden]) a", { timeout: 60000 }).catch(() => null);
  line = ((await page.textContent("#k-paid").catch(() => "")) || "").replace(/\s+/g, " ").trim();
  href = (await page.getAttribute("#k-paid a", "href").catch(() => "")) || "";
} finally {
  await browser.close();
}
const sig = (href.match(/explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})\?cluster=devnet/) || [])[1];
let status = null;
if (sig) {
  const r = await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignatureStatuses", params: [[sig], { searchTransactionHistory: true }] }) });
  status = ((await r.json()).result || {}).value?.[0] || null;
}
const units = (line.match(/paid ([\d.]+) test units/) || [])[1];
const ok = !!sig && !!units && status && ["confirmed", "finalized"].includes(status.confirmationStatus) && status.err === null;
lines.push(`front door: ${line || "(no payout line)"}`, `link: ${href || "(none)"}`, `devnet: ${status ? `${status.confirmationStatus}, err ${JSON.stringify(status.err)}, slot ${status.slot}` : "no status"}`);
lines.push(ok ? `PASS test_agent_paid_visible: ${units} test units, transaction ${sig.slice(0, 8)}... ${status.confirmationStatus} on devnet (slot ${status.slot})`
              : `FAIL test_agent_paid_visible: ${!sig ? "no transaction link on the front door" : !units ? "no amount" : "the transaction is not confirmed on devnet"}`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(ok ? 0 : 1);
