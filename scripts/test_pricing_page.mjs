// test_pricing_page, live: https://drexthealpha.github.io/Knos/pricing.html says the demand check is free, the 1% Knos
// takes of each payout it releases at mainnet, and nothing real charged on devnet; it shows the fee field the knos_pay
// source holds (programs-v2/knos_pay/src/lib.rs, FEE_BPS) at its value there; it cites 3 market figures, each with its
// year and a working link; the front door links it; and it says nothing about hackathons or judges.
//
//   node scripts/test_pricing_page.mjs
import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";

const PAGE = "https://drexthealpha.github.io/Knos/pricing.html", FRONT = "https://drexthealpha.github.io/Knos/";
const OUT = `${process.env.KNOS_WORLD || "C:/Users/zulab/knos-v1-private/v0328/world"}/test_pricing_page.txt`;
const fee = Number((readFileSync(new globalThis.URL("../programs-v2/knos_pay/src/lib.rs", import.meta.url), "utf8").match(/pub const FEE_BPS: u64 = (\d+);/) || [])[1]);
const lines = [];
let fails = 0;
const ok = (c, what, got) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}${got === undefined ? "" : ` ${JSON.stringify(got).slice(0, 200)}`}`); if (!c) fails++; };
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const r = await page.goto(PAGE, { waitUntil: "load" });
  ok(r && r.ok(), "the page answers", r && r.status());
  const g = await page.evaluate(() => ({ text: document.body.innerText,
    rows: [...document.querySelectorAll("table tbody tr")].map((tr) => ({ cells: [...tr.cells].map((c) => c.innerText.trim()), href: tr.querySelector("a")?.href })) }));
  ok(/demand check is free/i.test(g.text), "the demand check is free");
  ok(/at mainnet, Knos takes 1% of each payout it releases/i.test(g.text), "1% of each payout at mainnet");
  ok(/devnet test money, nothing real is charged/i.test(g.text), "nothing charged on devnet test money");
  ok(fee > 0 && g.text.includes(`FEE_BPS = ${fee}`), `the program's fee field at its source value, FEE_BPS = ${fee}`);
  ok(g.rows.length === 3 && g.rows.every((x) => /^20\d\d$/.test(x.cells[2]) && x.href), `3 market figures, each with a year and a link`, g.rows.map((x) => x.cells[2]));
  ok(!/hackathon|judges?\b|colosseum/i.test(g.text), "nothing about hackathons or judges");
  for (const x of g.rows) {
    let code = 0;
    try { code = (await fetch(x.href, { redirect: "follow", headers: { "User-Agent": "knos-link-check drexthealpha" }, signal: AbortSignal.timeout(60000) })).status; } catch { code = 0; }
    if (code === 403 || code === 429 || code === 0) {
      const tab = await browser.newPage();
      try { code = (await tab.goto(x.href, { waitUntil: "load", timeout: 60000 }))?.status() || 0; } catch { code = 0; } finally { await tab.close(); }
    }
    ok(code >= 200 && code < 400, `source answers ${code}: ${x.href}`);
  }
  const front = await browser.newPage();
  await front.goto(FRONT, { waitUntil: "load" });
  ok(await front.evaluate(() => [...document.querySelectorAll("a[href]")].some((a) => a.href === "https://drexthealpha.github.io/Knos/pricing.html")), "the front door links the page");
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_pricing_page: ${fails} check(s) failed` : `PASS test_pricing_page: free check, 1% at mainnet, FEE_BPS ${fee} shown, 3 market sources with years and working links, linked from the front door`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
