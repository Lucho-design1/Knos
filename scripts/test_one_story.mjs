// test_one_story, live: the front door, the live app's home and the README on main each show the four steps in this
// order and these words: Check demand, Ready brief, Money held, Paid on proof; under Paid on proof, the live agent
// payout (a link to its transaction on Solana's explorer, devnet).
//
//   node scripts/test_one_story.mjs
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_one_story.txt`;
const STEPS = ["Check demand", "Ready brief", "Money held", "Paid on proof"];
const TX = /https:\/\/explorer\.solana\.com\/tx\/[1-9A-HJ-NP-Za-km-z]{64,90}\?cluster=devnet/;
const lines = [];
let bad = 0;
const judge = (name, heads, under) => {
  const inOrder = heads.length === 4 && heads.every((h, i) => h === STEPS[i]);
  const ok = inOrder && TX.test(under);
  if (!ok) bad++;
  lines.push(`${ok ? "ok  " : "FAIL"} ${name}: steps ${JSON.stringify(heads)}; payout under Paid on proof ${TX.test(under) ? "yes" : "no"}`);
};
const browser = await chromium.launch();
try {
  for (const [name, url] of [["front door", "https://drexthealpha.github.io/Knos/"], ["live app home", "https://knos.onrender.com/"]]) {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: "load", timeout: 120000 });
    const g = await page.evaluate(() => ({ heads: [...document.querySelectorAll("#k-steps .k-step-list > li > h3")].map((h) => h.textContent.trim()),
      under: [...document.querySelectorAll("#paid-on-proof a[href]")].map((a) => a.href).join(" ") }));
    judge(name, g.heads, g.under);
    await page.close();
  }
} finally {
  await browser.close();
}
const md = await (await fetch(`https://raw.githubusercontent.com/drexthealpha/Knos/main/README.md?t=${Date.now()}`)).text();
const items = [...md.matchAll(/^\d+\. \*\*([^*]+?)\.\*\*(.*)$/gm)].map((m) => [m[1], m[2]]);
const i = items.findIndex((x) => x[0] === STEPS[0]);
const four = i < 0 ? [] : items.slice(i, i + 4);
judge("README", four.map((x) => x[0]), (four[3] || [])[1] || "");
lines.push(bad ? `FAIL test_one_story: ${bad} of 3 pages miss a step, are out of order or lack the payout` : "PASS test_one_story: 0 of 3 pages (front door, app home, README) miss a step or the payout under Paid on proof");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(bad ? 1 : 0);
