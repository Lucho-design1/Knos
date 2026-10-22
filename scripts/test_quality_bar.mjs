// test_quality_bar, live, on a GitHub runner (.github/workflows/quality.yml):
//
//   node scripts/test_quality_bar.mjs axe            axe-core on every public page (scripts/public_pages.json), at 375 and
//                                                    1280, light and dark: 0 violations
//   node scripts/test_quality_bar.mjs lighthouse <dir>   the cold Lighthouse runs .lighthouseci/ holds: every public page
//                                                    measured 3 times, accessibility 100 and performance at least 95 in each
//   node scripts/test_quality_bar.mjs vitals <dir>       test_vitals, from the same runs: LCP <= 1.5 s, CLS <= 0.05 and
//                                                    TBT <= 100 ms in each of the 3 cold runs of every public page
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";

const PAGES = JSON.parse(readFileSync(new URL("./public_pages.json", import.meta.url), "utf8")).pages;
let fails = 0;
const ok = (c, msg, extra) => { console.log((c ? "ok   " : "FAIL ") + msg + (extra === undefined ? "" : " " + JSON.stringify(extra))); if (!c) fails += 1; };

if (process.argv[2] === "axe") {
  const { chromium } = await import("playwright");
  const axe = readFileSync(createRequire(import.meta.url).resolve("axe-core/axe.min.js"), "utf8");
  const browser = await chromium.launch();
  let total = 0;
  for (const url of PAGES) {
    for (const [w, h] of [[375, 812], [1280, 800]]) {
      for (const scheme of ["light", "dark"]) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme });
        const page = await ctx.newPage();
        if (/wanted\.html/.test(url)) await page.route(/onrender\.com/, (r) => r.abort());       // the wake page, as itself
        await page.goto(url, { waitUntil: "load", timeout: 120000 });
        await page.waitForTimeout(1500);
        await page.addScriptTag({ content: axe });
        const v = await page.evaluate(async () => (await window.axe.run(document, { resultTypes: ["violations"] })).violations
          .map((x) => ({ id: x.id, impact: x.impact, nodes: x.nodes.length, at: x.nodes.slice(0, 2).map((n) => n.target.join(" ")) })));
        total += v.length;
        ok(v.length === 0, `axe ${scheme} ${w}px ${url}: ${v.length} violations`, v.length ? v : undefined);
        await ctx.close();
      }
    }
  }
  await browser.close();
  console.log(`axe violations: ${total}`);
} else if (process.argv[2] === "lighthouse") {
  const dir = process.argv[3] || ".lighthouseci";
  const runs = readdirSync(dir).filter((f) => /^lhr-.*\.json$/.test(f)).map((f) => JSON.parse(readFileSync(`${dir}/${f}`, "utf8")));
  for (const url of PAGES) {
    const mine = runs.filter((r) => r.requestedUrl === url);
    const s = mine.map((r) => [Math.round(r.categories.accessibility.score * 100), Math.round(r.categories.performance.score * 100)]);
    for (const r of mine) {
      const a = (k) => r.audits[k]?.displayValue || "-";
      console.log(`     ${url} FCP ${a("first-contentful-paint")} LCP ${a("largest-contentful-paint")} TBT ${a("total-blocking-time")} CLS ${a("cumulative-layout-shift")} SI ${a("speed-index")}`
        + ` | failing a11y: ${Object.values(r.audits).filter((x) => r.categories.accessibility.auditRefs.some((ref) => ref.id === x.id) && x.score === 0).map((x) => x.id).join(",") || "none"}`);
    }
    ok(mine.length >= 3 && s.every(([a, p]) => a === 100 && p >= 95), `lighthouse ${url}: ${mine.length} cold runs, accessibility/performance`, s.map(([a, p]) => `${a}/${p}`));
  }
} else if (process.argv[2] === "vitals") {
  const dir = process.argv[3] || ".lighthouseci";
  const runs = readdirSync(dir).filter((f) => /^lhr-.*\.json$/.test(f)).map((f) => JSON.parse(readFileSync(`${dir}/${f}`, "utf8")));
  for (const url of PAGES) {
    const mine = runs.filter((r) => r.requestedUrl === url);
    const v = mine.map((r) => ({ lcp: Math.round(r.audits["largest-contentful-paint"].numericValue), cls: +r.audits["cumulative-layout-shift"].numericValue.toFixed(3),
                                 tbt: Math.round(r.audits["total-blocking-time"].numericValue) }));
    ok(mine.length >= 3 && v.every((x) => x.lcp <= 1500 && x.cls <= 0.05 && x.tbt <= 100), `vitals ${url}: ${mine.length} cold runs, LCP ms / CLS / TBT ms`,
       v.map((x) => `${x.lcp}/${x.cls}/${x.tbt}`));
  }
  console.log(fails ? `FAIL test_vitals (${fails})` : "PASS test_vitals");
  process.exit(fails ? 1 : 0);
} else {
  console.error("usage: node scripts/test_quality_bar.mjs axe | lighthouse <.lighthouseci> | vitals <.lighthouseci>");
  process.exit(2);
}
console.log(fails ? `FAIL test_quality_bar (${fails})` : "PASS test_quality_bar");
process.exit(fails ? 1 : 0);
