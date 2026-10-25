// test_both_stories, live: the front door carries both stories on one page. Its raw HTML holds exactly 1 h1, the
// buyer's headline. The Paid on proof step says, verbatim, "GitHub signs which checks ran, and a Solana program checks
// that signature itself before it pays.", links the newest knos_oidc signature check and the newest agent payout,
// both confirmed on devnet, and sits fully within the first 2 screen heights at 1280x800 and 390x844, with none of the
// words for further down on the first screen. Its "Check a pull request" opens the checker (heading h2), which checks
// a public pull request.
//
//   node scripts/test_both_stories.mjs
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const FRONT = "https://drexthealpha.github.io/Knos/";
const OUT = `${process.env.KNOS_WORLD || "C:/Users/zulab/knos-v1-private/v0328/world"}/test_both_stories.txt`;
const HEAD = "See who wants your product, and where, before you build it";
const SENTENCE = "GitHub signs which checks ran, and a Solana program checks that signature itself before it pays.";
const PR = "https://github.com/drexthealpha/knos-e2e/pull/266";
const BANNED = /\b(valley|escrow|devnet|solana|kardashev|proof|milestone|referee)\b/gi;
const lines = [];
let fails = 0;
const ok = (c, what, got) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}${got === undefined ? "" : ` ${JSON.stringify(got).slice(0, 220)}`}`); if (!c) fails++; };
const status = async (sig) => {
  const r = await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignatureStatuses", params: [[sig], { searchTransactionHistory: true }] }) });
  return ((await r.json()).result || {}).value?.[0] || null;
};

const raw = await (await fetch(FRONT + `?raw=${Date.now()}`)).text();
const h1s = [...raw.matchAll(/<h1\b[^>]*>([\s\S]*?)<\/h1>/g)].map((m) => m[1].replace(/<[^>]+>/g, "").trim());
ok(h1s.length === 1 && h1s[0] === HEAD, `raw HTML: ${h1s.length} h1`, h1s);
const browser = await chromium.launch();
try {
  for (const [w, h] of [[1280, 800], [390, 844]]) {
    const page = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
    await page.goto(FRONT, { waitUntil: "load" });
    await page.waitForTimeout(1500);
    const g = await page.evaluate(() => {
      const H = innerHeight, step = document.getElementById("paid-on-proof"), b = step.getBoundingClientRect(), seen = [];
      const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        const t = n.textContent.trim(); if (!t || !n.parentElement.checkVisibility()) continue;
        const r = document.createRange(); r.selectNodeContents(n); const bb = r.getBoundingClientRect();
        if (bb.height && bb.top < H && bb.bottom > 0) seen.push(t);
      }
      return { top: b.top + scrollY, bottom: b.bottom + scrollY, H, first: seen.join(" "), text: document.body.innerText,
        oidc: step.querySelector("#k-oidc a")?.href || "", paid: step.querySelector("#k-paid a")?.href || "",
        check: !!step.querySelector('a[href*="#check-a-pull-request"]') };
    });
    ok(g.bottom <= 2 * g.H, `${w}px: Paid on proof fully within 2 screen heights (${Math.round(g.top)} to ${Math.round(g.bottom)} of ${2 * g.H})`);
    const bad = [...new Set((g.first.match(BANNED) || []).map((x) => x.toLowerCase()))];
    ok(bad.length === 0, `${w}px: none of the words for further down on the first screen`, bad);
    if (w === 1280) {
      ok(g.text.includes(SENTENCE), "the sentence, verbatim, in the rendered text");
      for (const [what, href] of [["knos_oidc signature check", g.oidc], ["agent payout", g.paid]]) {
        const sig = (href.match(/explorer\.solana\.com\/tx\/([1-9A-HJ-NP-Za-km-z]{64,90})\?cluster=devnet/) || [])[1];
        const st = sig ? await status(sig) : null;
        ok(!!st && ["confirmed", "finalized"].includes(st.confirmationStatus) && st.err === null, `${what}: ${sig ? sig.slice(0, 10) + "..." : "no link"} ${st ? st.confirmationStatus : "no status"} on devnet`);
      }
      ok(g.check, 'the step links "Check a pull request"');
      await page.click('#paid-on-proof a[href*="#check-a-pull-request"]');
      await page.waitForSelector("#view-check", { state: "visible", timeout: 30000 });
      const head = await page.evaluate(() => { const e = document.getElementById("check"); return e ? [e.tagName, e.textContent.trim()] : null; });
      ok(head && head[0] === "H2", "the checker opens, its heading an h2", head);
      await page.fill("#fd-in", PR);
      await page.click('#front-door button[data-fd="run"]');
      const done = await page.waitForSelector('#front-result .fd-line:not([data-state="pending"])', { timeout: 120000 }).then(() => true).catch(() => false);
      const res = done ? await page.evaluate(() => [...document.querySelectorAll("#front-result .fd-line")].map((li) => li.dataset.state + ": " + li.textContent.replace(/\s+/g, " ").trim().slice(0, 90))) : [];
      ok(done, `the public pull request is checked (${PR})`, res);
    }
    await page.context().close();
  }
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_both_stories: ${fails} check(s) failed` : "PASS test_both_stories: 1 h1, the signing sentence verbatim, 2 links confirmed on devnet, Paid on proof within 2 screens at 1280 and 390, the pull-request checker runs");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
