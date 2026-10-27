// test_layout_stable, live: the layout holds still. Cumulative layout shift under 0.05 on the front door, /app/ and a
// result page /r/<id>, at 390 and 1280 px, over the load and 4 s after it (the result card arriving included); no button or
// sign-in link cut off; no map tile asked for before its map is in view; /proof/'s CSS under 65,000 bytes; each select
// drawn with the design tokens (its border and its radius from them, not the browser's).
//   node scripts/test_layout_stable.mjs <commit sha under test>      (KNOS_DRY=1: print, write no result)
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_layout_stable.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
// a recorded result's own page: the sample the front door shows first
const proof = await (await fetch(`${API}/api/proof`)).json().catch(() => ({}));
const rid = String(proof.hash || proof.report || (proof.proof || {}).hash || "").slice(0, 16);
const PAGES = [["the front door", SITE], ["/app/", `${API}/app/`], [`/r/${rid}`, `${API}/r/${rid}`]];
const browser = await chromium.launch();
const errors = [];
let worst = 0, cut = 0, early = 0;
try {
  for (const [name, url] of PAGES) {
    for (const width of [390, 1280]) {
      const ctx = await browser.newContext({ viewport: { width, height: 844 } });
      const tiles = [];
      ctx.on("request", (r) => { if (/tile\.openstreetmap\.org/.test(r.url())) tiles.push(r.url()); });
      await ctx.addInitScript(() => { window.__cls = 0;
        new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true }); });
      const p = await ctx.newPage();
      p.on("pageerror", (e) => errors.push(`${name} ${width}: ${e.message}`));
      await p.goto(url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(), { waitUntil: "domcontentloaded", timeout: 90000 });
      await p.waitForLoadState("load", { timeout: 60000 }).catch(() => {});
      await p.waitForTimeout(4000);
      const s = await p.evaluate(() => {
        const H = innerHeight;
        const maps = [...document.querySelectorAll(".k-osm")].map((m) => m.getBoundingClientRect()).filter((r) => r.width > 0);
        const inView = maps.some((r) => r.top < H && r.bottom > 0);
        // a control cut off: its text wider than its box, or its box past the window's edge
        const cut = [...document.querySelectorAll("button, a.signin, #whoBtn, .k-cta, a[role=button]")].filter((b) => b.checkVisibility && b.checkVisibility())
          .filter((b) => { const r = b.getBoundingClientRect(); return b.scrollWidth > b.clientWidth + 1 || r.right > innerWidth + 1 || r.left < -1; })
          .map((b) => (b.textContent || b.getAttribute("aria-label") || "").trim().slice(0, 30));
        const selects = [...document.querySelectorAll("select")].filter((x) => x.checkVisibility && x.checkVisibility()).map((x) => {
          const c = getComputedStyle(x); return { radius: c.borderTopLeftRadius, border: c.borderTopStyle, appearance: c.appearance }; });
        return { cls: Math.round(window.__cls * 10000) / 10000, inView, maps: maps.length, cut, selects };
      });
      const before = s.inView ? 0 : tiles.length;
      worst = Math.max(worst, s.cls); cut += s.cut.length; early += before;
      ok(s.cls < 0.05, `${name} at ${width}: layout shift ${s.cls}`);
      ok(s.cut.length === 0, `${name} at ${width}: ${s.cut.length} control(s) cut off${s.cut.length ? ` (${s.cut.slice(0, 3).join(" | ")})` : ""}`);
      ok(before === 0, `${name} at ${width}: ${tiles.length} map tile request(s), ${s.maps} map(s), ${s.inView ? "a map in view" : "no map in view"}`);
      if (s.selects.length) ok(s.selects.every((x) => x.radius !== "0px" && x.border === "solid"), `${name} at ${width}: ${s.selects.length} select(s) drawn with the tokens (${JSON.stringify(s.selects[0])})`);
      await ctx.close();
    }
  }
  // /proof/: its CSS, linked and written into the page
  const html = await (await fetch(`${SITE}proof/?t=${Date.now()}`)).text();
  let css = [...html.replace(/<script\b[\s\S]*?<\/script>/g, "").matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].reduce((n, m) => n + Buffer.byteLength(m[1]), 0);
  for (const m of html.matchAll(/<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"/g)) css += (await (await fetch(new URL(m[1], `${SITE}proof/`))).arrayBuffer()).byteLength;
  ok(css > 0 && css < 65000, `/proof/: ${css} bytes of CSS (under 65,000)`);
} catch (e) {
  ok(false, `the browser step stopped: ${String(e.message).split("\n")[0].slice(0, 160)}`);
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 2).join("; ").slice(0, 200)})` : ""}`);
lines.push(fails ? `FAIL test_layout_stable: ${fails} check(s) failed`
  : `PASS test_layout_stable: worst layout shift ${worst} on 3 pages at 2 widths; ${cut} controls cut off; ${early} tile requests before a map is in view`);
console.log(lines.join("\n"));
if (!process.env.KNOS_DRY) appendFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
