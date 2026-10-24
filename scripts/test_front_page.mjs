// test_front_page, live: the first screen of the front door (https://drexthealpha.github.io/Knos/) at 390 and 1280 px
// names one buyer ("someone about to build a product") and one action ("Check demand"), and says none of the words
// that belong further down (valley, escrow, devnet, Solana, Kardashev, proof, milestone, referee). Further down the
// page still carries the mission, the science and Solana. The measured strip and "pre-ordered" are gone.
//
//   node scripts/test_front_page.mjs [url]
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const URL = process.argv[2] || "https://drexthealpha.github.io/Knos/";
const OUT = process.env.KNOS_WORLD ? `${process.env.KNOS_WORLD}/test_front_page.txt` : "C:/Users/zulab/knos-v1-private/v0328/world/test_front_page.txt";
const BANNED = /\b(valley|escrow|devnet|solana|kardashev|proof|milestone|referee)\b/gi;
const lines = [];
let fails = 0;
const ok = (c, what, got) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}${got === undefined ? "" : ` ${JSON.stringify(got).slice(0, 300)}`}`); if (!c) fails++; };

const browser = await chromium.launch();
try {
  for (const [w, h] of [[390, 844], [1280, 800]]) {
    const page = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
    await page.goto(URL, { waitUntil: "load" });
    await page.waitForTimeout(1500);
    const got = await page.evaluate(() => {
      const H = innerHeight, W = innerWidth, seen = [];
      const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        const t = n.textContent.replace(/\s+/g, " ").trim();
        if (!t || !n.parentElement || !n.parentElement.checkVisibility({ visibilityProperty: true, opacityProperty: true })) continue;
        const r = document.createRange(); r.selectNodeContents(n);
        const b = r.getBoundingClientRect();
        if (b.width && b.height && b.bottom > 0 && b.top < H && b.right > 0 && b.left < W) seen.push(t);
      }
      const btn = [...document.querySelectorAll("button, a")].find((e) => /^check demand$/i.test(e.textContent.trim()) && e.checkVisibility()
        && e.getBoundingClientRect().top < H && e.getBoundingClientRect().bottom > 0 && e.closest("#k-hero"));
      return { first: seen.join(" "), button: !!btn, all: document.body.innerText, strip: !!document.querySelector("#view-home .k-vectors, #k-hero .k-vectors") };
    });
    ok(/someone about to build a product/i.test(got.first), `${w}px: the first screen names the buyer, someone about to build a product`);
    ok(got.button, `${w}px: one action on the first screen, "Check demand"`);
    const bad = [...new Set((got.first.match(BANNED) || []).map((x) => x.toLowerCase()))];
    ok(bad.length === 0, `${w}px: none of the words for further down is on the first screen`, bad);
    ok(/valley of death/i.test(got.all) && /science/i.test(got.all) && /solana/i.test(got.all), `${w}px: the mission, the science and Solana are further down the page`);
    ok(!got.strip && !/pre-ordered/i.test(got.all), `${w}px: no measured strip, no "pre-ordered" on the cards`);
  }
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_front_page: ${fails} check(s) failed at 390 and 1280 px` : "PASS test_front_page: buyer and \"Check demand\" on the first screen at 390 and 1280 px, 0 words for further down, mission and Solana below");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
