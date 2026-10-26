// test_public_text, live: no email address and no visible "escrow" in what the public reads. HTML pages are read as
// Playwright's innerText (what a reader sees); JSON answers by their text values (field names such as escrow_target
// may stay). Counts only: a matched value is never printed.
//
//   node scripts/test_public_text.mjs
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_public_text.txt`;
const APP = "https://knos.onrender.com";
const PAGES = ["https://drexthealpha.github.io/Knos/", `${APP}/`, "https://drexthealpha.github.io/Knos/how-we-test.html",
  "https://drexthealpha.github.io/Knos/pricing.html", `${APP}/invite`, `${APP}/with-without`];
// the public answers that list sessions, solvers, outside people or projects, and the check's own output
const JSON_GET = ["/api/solvers", "/api/outside", "/api/crossings", "/api/projects?take=100", "/api/front", "/api/agent/payout/latest", "/api/usage"];
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const ESCROW = /escrow/gi;
const values = (o) => (typeof o === "string" ? [o] : Array.isArray(o) ? o.flatMap(values) : o && typeof o === "object" ? Object.values(o).flatMap(values) : []);
const count = (texts) => ({ emails: texts.reduce((n, t) => n + (t.match(EMAIL) || []).length, 0), escrow: texts.reduce((n, t) => n + (t.match(ESCROW) || []).length, 0) });
const lines = [];
let emails = 0, escrow = 0;
const add = (what, c) => { emails += c.emails; escrow += c.escrow; lines.push(`${c.emails || c.escrow ? "FAIL" : "ok  "} ${what}: ${c.emails} email, ${c.escrow} escrow`); };

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  for (const url of PAGES) {
    await page.goto(url, { waitUntil: "load", timeout: 120000 });
    await page.waitForTimeout(1500);
    await page.mouse.move(200, 300);              // the reader's first move: the live lines (payout, counter) are asked
    await page.waitForTimeout(2500);
    add(url, count([await page.evaluate(() => document.body.innerText)]));
  }
} finally {
  await browser.close();
}
for (const p of JSON_GET) {
  const r = await fetch(APP + p, { headers: { "User-Agent": "knos-test" } });
  add(`${p} (${r.status})`, count(values(await r.json())));
}
const rep = await (await fetch(`${APP}/api/check`, { method: "POST", headers: { "Content-Type": "application/json", "User-Agent": "knos-test" },
  body: JSON.stringify({ idea: "a ceramic mug that keeps coffee warm" }) })).json();
add("/api/check text, a ceramic mug that keeps coffee warm", count(values(rep)));
lines.push(emails || escrow ? `FAIL test_public_text: ${emails} email matches and ${escrow} visible "escrow" across ${PAGES.length} pages and ${JSON_GET.length + 1} answers`
                            : `PASS test_public_text: 0 email matches and 0 visible "escrow" across ${PAGES.length} pages and ${JSON_GET.length + 1} answers`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(emails || escrow ? 1 : 0);
