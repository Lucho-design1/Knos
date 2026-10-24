// test_how_we_test, live: the page "How we test Knos" (https://drexthealpha.github.io/Knos/how-we-test.html) has a
// section for each published claim (with and without Qloo, Kickstarter, the past research awards, the ranked run and
// an agent's payout), each section links its run, and every link on the page answers (0 broken).
//
//   node scripts/test_how_we_test.mjs [url]
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const URL = process.argv[2] || "https://drexthealpha.github.io/Knos/how-we-test.html";
const OUT = process.env.KNOS_WORLD ? `${process.env.KNOS_WORLD}/test_how_we_test.txt` : "C:/Users/zulab/knos-v1-private/v0328/world/test_how_we_test.txt";
const NEED = { "with-without": /onrender\.com\/(with-without|api\/qloo-diff)/, kickstarter: /kickstarter_truth/, sbir: /outside_truth\.json/,
  ranked: /qloo_lift_ranked\.json/, payout: /explorer\.solana\.com\/tx\/[1-9A-HJ-NP-Za-km-z]{64,90}\?cluster=devnet/ };
const lines = [];
let fails = 0;
const browser = await chromium.launch();
let got;
try {
  const page = await browser.newPage();
  const r = await page.goto(URL, { waitUntil: "load" });
  if (!r || !r.ok()) throw new Error(`the page answered ${r && r.status()}`);
  got = await page.evaluate(() => ({ h1: document.querySelector("h1")?.textContent.trim(),
    links: [...document.querySelectorAll("a[href]")].map((a) => a.href).filter((h) => /^https?:/.test(h)),
    secs: Object.fromEntries([...document.querySelectorAll("section.t[id]")].map((s) => [s.id, [...s.querySelectorAll("a[href]")].map((a) => a.href)])) }));
} finally {
  await browser.close();
}
if (got.h1 !== "How we test Knos") { fails++; lines.push(`FAIL h1 ${JSON.stringify(got.h1)}`); }
for (const [id, re] of Object.entries(NEED)) {
  const ok = (got.secs[id] || []).some((h) => re.test(h));
  if (!ok) fails++;
  lines.push(`${ok ? "ok  " : "FAIL"} ${id}: ${(got.secs[id] || []).length} links`);
}
const uniq = [...new Set(got.links.map((h) => h.split("#")[0]))];
let broken = 0;
for (const u of uniq) {
  let code = 0;
  for (let t = 0; t < 2 && !(code >= 200 && code < 400); t++) {
    try { code = (await fetch(u, { redirect: "follow", signal: AbortSignal.timeout(90000), headers: { "User-Agent": "knos-link-check" } })).status; } catch { code = 0; }
  }
  const ok = code >= 200 && code < 400;
  if (!ok) broken++;
  lines.push(`${ok ? "ok  " : "FAIL"} ${code} ${u}`);
}
if (broken) fails++;
lines.push(fails ? `FAIL test_how_we_test: ${broken} broken of ${uniq.length} links, ${fails} check(s) failed`
                 : `PASS test_how_we_test: ${Object.keys(NEED).length} claims each linked to its run, ${uniq.length} links, 0 broken`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
