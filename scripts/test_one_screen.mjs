// test_one_screen, live: the front door's first screen (390x844 and 1280x800, DOM text plus a screenshot) carries the
// headline exactly, one text input and at least 3 sample chips that fill it, and none of the words for further down.
// A chip's check draws one result card on the same page: an OpenStreetMap map with at least 3 cities of Qloo's heatmap,
// the matched audience, "They also love" in at least 2 Qloo domains, and a fold that opens Claude's answer alone.
// Below the first screen, the step "Paid on proof" holds pull-request checks, Solana and pricing. The live app's top
// navigation has at most 7 items, the rest under one "More".
//
//   node scripts/test_one_screen.mjs
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const FRONT = "https://drexthealpha.github.io/Knos/", APP = "https://knos.onrender.com/app/";
const WORLD = process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`;
const HEAD = "See who wants your product, and where, before you build it";
const BANNED = /\b(valley|escrow|devnet|solana|kardashev|proof|milestone|referee)\b/gi;
const lines = [];
let fails = 0;
const ok = (c, what, got) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}${got === undefined ? "" : ` ${JSON.stringify(got).slice(0, 240)}`}`); if (!c) fails++; };

const browser = await chromium.launch();
try {
  for (const [w, h] of [[390, 844], [1280, 800]]) {
    const page = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
    await page.goto(FRONT, { waitUntil: "load" });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${WORLD}/test_one_screen-${w}.png` });
    const s = await page.evaluate(() => {
      const H = innerHeight, seen = [], vis = (e) => e.checkVisibility({ visibilityProperty: true, opacityProperty: true });
      const inFirst = (e) => { const b = e.getBoundingClientRect(); return b.width && b.height && b.bottom > 0 && b.top < H; };
      const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        const t = n.textContent.replace(/\s+/g, " ").trim();
        if (!t || !n.parentElement || !vis(n.parentElement)) continue;
        const r = document.createRange(); r.selectNodeContents(n);
        const b = r.getBoundingClientRect();
        if (b.width && b.height && b.bottom > 0 && b.top < H) seen.push(t);
      }
      const inputs = [...document.querySelectorAll("input")].filter((i) => !["hidden", "checkbox", "radio", "submit", "button"].includes(i.type) && vis(i) && inFirst(i));
      const chips = [...document.querySelectorAll("#k-hero .k-try .k-chip[data-q]")].filter((c) => vis(c) && inFirst(c));
      const step = document.getElementById("paid-on-proof");
      return { h1: document.querySelector("#k-mission")?.textContent.trim(), h1first: inFirst(document.querySelector("#k-mission")),
        first: seen.join(" "), inputs: inputs.map((i) => i.id), chips: chips.map((c) => c.dataset.q),
        step: step ? { top: step.getBoundingClientRect().top + scrollY, text: step.textContent.replace(/\s+/g, " "), pricing: !!step.querySelector('a[href*="pricing"]') } : null };
    });
    ok(s.h1 === HEAD && s.h1first, `${w}px: the headline, exactly, on the first screen`, s.h1);
    ok(s.inputs.length === 1 && s.inputs[0] === "k-q", `${w}px: one text input on the first screen`, s.inputs);
    ok(s.chips.length >= 3, `${w}px: ${s.chips.length} sample chips on the first screen`);
    const bad = [...new Set((s.first.match(BANNED) || []).map((x) => x.toLowerCase()))];
    ok(bad.length === 0, `${w}px: none of the words for further down on the first screen`, bad);
    ok(!!s.step && s.step.top >= h && /pull request/i.test(s.step.text) && /solana/i.test(s.step.text) && s.step.pricing,
       `${w}px: "Paid on proof" below the first screen with pull-request checks, Solana and pricing`, s.step && { top: Math.round(s.step.top) });
    // a chip fills the box and the check answers on this page with one card
    const chip = page.locator('#k-hero .k-chip[data-q="an AI recipe planner for families"]');
    await chip.click();
    const filled = await page.inputValue("#k-q");
    ok(filled === "an AI recipe planner for families", `${w}px: a chip fills the input`, filled);
    const card = await page.waitForSelector("#k-card .k-card", { timeout: 180000 }).then(() => true).catch(() => false);
    await page.waitForTimeout(800);
    const c = await page.evaluate(() => ({ cards: document.querySelectorAll("#k-card .k-card").length, url: location.href,
      tiles: [...document.querySelectorAll("#k-card .k-osm img.k-tile")].filter((i) => i.src.startsWith("https://tile.openstreetmap.org/")).length,
      pins: document.querySelectorAll("#k-card .k-osm .k-pin").length, heat: Number(document.querySelector('#k-card [data-part="cities"]')?.dataset.heat || 0),
      audience: (document.querySelector('#k-card [data-part="audience"]')?.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120),
      domains: [...new Set([...document.querySelectorAll("#k-card .k-also[data-domain]")].map((e) => e.dataset.domain))] }));
    ok(card && c.cards === 1 && c.url.startsWith(FRONT), `${w}px: one result card on the same page`);
    ok(c.tiles > 0 && c.pins >= 3 && c.heat >= 3, `${w}px: OpenStreetMap map with ${c.pins} pins, ${c.heat} of them Qloo heatmap cities`, { tiles: c.tiles, pins: c.pins, heat: c.heat });
    ok(c.audience.length > 12 && !/did not answer/i.test(c.audience), `${w}px: the matched audience`, c.audience);
    ok(c.domains.length >= 2, `${w}px: "They also love" in ${c.domains.length} Qloo domains`, c.domains);
    const fold = await page.$("#k-card details[data-claude] > summary");
    if (fold) await fold.click();
    const vs = fold ? await page.waitForSelector("#k-card [data-claude-body] .k-vs", { timeout: 30000 }).then(() => true).catch(() => false) : false;
    ok(vs, `${w}px: the toggle shows Claude's answer alone beside Knos's`);
    await page.context().close();
  }
  // the live app's top navigation
  const app = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  await app.goto(APP, { waitUntil: "load" });
  const nav = await app.evaluate(() => {
    const n = document.querySelector("header nav#nav");
    const top = [...n.children].filter((e) => !e.matches(".more")).map((e) => e.textContent.trim());
    const more = [...n.querySelectorAll(":scope > .more")].map((e) => e.querySelector("button")?.textContent.trim());
    return { top, more };
  });
  const items = nav.top.length + nav.more.length;
  ok(items <= 7 && nav.more.length === 1 && nav.more[0] === "More", `live app: ${items} top navigation items, the rest under one "More"`, nav);
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_one_screen: ${fails} check(s) failed at 390 and 1280 px` : "PASS test_one_screen: headline, 1 input, chips and one result card (map of heatmap cities, audience, 2 domains, Claude toggle) at 390 and 1280 px, 0 banned words, app menu within 7");
console.log(lines.join("\n"));
writeFileSync(`${WORLD}/test_one_screen.txt`, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
