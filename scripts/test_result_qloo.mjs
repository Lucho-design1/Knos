// test_result_qloo, live: each of the 20 ideas of the Qloo comparison, asked in the front door's box, comes back as a
// card with where to launch on OpenStreetMap's tiles (at least 3 marked cities), what its people also love in at least
// 2 Qloo domains, and a fold "Claude alone" that opens on Claude's answer beside Knos's.
//
//   node scripts/test_result_qloo.mjs [url]
import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";

const URL = process.argv[2] || "https://drexthealpha.github.io/Knos/";
const OUT = process.env.KNOS_WORLD ? `${process.env.KNOS_WORLD}/test_result_qloo.txt` : "C:/Users/zulab/knos-v1-private/v0328/world/test_result_qloo.txt";
const src = readFileSync(new globalThis.URL("./qloo_vs_open_signals.py", import.meta.url), "utf8");
const IDEAS = [...src.slice(src.indexOf("IDEAS")).matchAll(/\("[A-Za-z0-9_ -]+",\s*"([^"]+)"\)/g)].map((m) => m[1]).slice(0, 20);
const lines = [];
let good = 0;
const browser = await chromium.launch();
try {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await page.goto(URL, { waitUntil: "load" });
  for (const idea of IDEAS) {
    let got = { tiles: 0, pins: 0, domains: [], claude: false, err: "" };
    try {
      await page.fill("#k-q", idea);
      await page.click("#k-go");
      await page.waitForSelector("#k-card .k-card", { timeout: 180000 });
      await page.waitForTimeout(500);
      got = await page.evaluate(() => ({
        tiles: [...document.querySelectorAll("#k-card .k-osm img.k-tile")].filter((i) => /^https:\/\/tile\.openstreetmap\.org\//.test(i.src)).length,
        pins: document.querySelectorAll("#k-card .k-osm .k-pin").length,
        domains: [...document.querySelectorAll("#k-card .k-also[data-domain]")].map((e) => e.dataset.domain), claude: false, err: "" }));
      const fold = await page.$("#k-card details[data-claude] > summary");
      if (fold) {
        await fold.click();
        got.claude = await page.waitForSelector("#k-card [data-claude-body] .k-vs", { timeout: 30000 }).then(() => true).catch(() => false);
      }
    } catch (e) {
      got.err = String(e.message || e).split("\n")[0].slice(0, 80);
    }
    const pass = got.tiles > 0 && got.pins >= 3 && new Set(got.domains).size >= 2 && got.claude;
    good += pass;
    lines.push(`${pass ? "ok  " : "FAIL"} ${idea.slice(0, 44).padEnd(44)} tiles ${got.tiles}, cities ${got.pins}, domains ${got.domains.join("+") || "none"}, Claude ${got.claude ? "beside" : "no"}${got.err ? ` (${got.err})` : ""}`);
  }
} finally {
  await browser.close();
}
lines.push(`${good === IDEAS.length ? "PASS" : "FAIL"} test_result_qloo: ${good} of ${IDEAS.length} ideas with a map of at least 3 cities, 2 Qloo domains and Claude alone beside Knos`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(good === IDEAS.length ? 0 : 1);
