// test_verdict_speed_cold, live, after a redeploy (the app's Qloo cache empty): on the front door, one warm-up idea,
// then 20 never-checked ideas in sequence. Time to verdict card: from the press that sends the request until the
// verdict text is visible. Time to full card: until the map or the no-map line is visible. Pass: p95 of time to
// verdict card at most 10.0 s (nearest rank, the 19th of 20). Reported, not a pass line: p50 and p95 of time to full
// card, and how many full cards hold Qloo heatmap cities.
//
//   node scripts/test_verdict_speed_cold.mjs
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const FRONT = "https://drexthealpha.github.io/Knos/";
const OUT = `${process.env.KNOS_WORLD || "C:/Users/zulab/knos-v1-private/v0328/world"}/test_verdict_speed_cold.txt`;
const WARM = "a hand-painted silk scarf";
const IDEAS = ["a robot lawn mower for small yards", "a protein bar made from crickets", "a language app for Yoruba learners",
  "a wireless guitar amplifier", "a kids' coding robot kit", "a luxury pet hotel", "a smart ring that tracks sleep",
  "an electric scooter rental for campuses", "a hot sauce made with scotch bonnet", "a 3D printed prosthetic hand", "a rooftop cinema",
  "a baby carrier for hot climates", "a cookbook of Nigerian street food", "a noise-cancelling sleep mask", "a mobile car wash service",
  "a retro arcade bar", "a refillable deodorant", "a drone photography course", "a plant-based ice cream shop", "a weighted blanket for kids"];
const rank = (xs, p) => [...xs].sort((a, b) => a - b)[Math.ceil(p * xs.length) - 1];
const lines = [];
const browser = await chromium.launch();
const verdict = [], full = [];
let heat = 0;
try {
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  await page.goto(FRONT, { waitUntil: "load" });
  const one = async (idea) => {
    await page.fill("#k-q", idea);
    const t0 = Date.now();
    await page.click("#k-go");
    await page.waitForFunction((i) => { const c = document.querySelector("#k-card .k-card"); const v = c?.querySelector(".k-verdict");
      return document.querySelector("#k-card")?.dataset.idea === i && v && v.checkVisibility() && v.textContent.trim(); }, idea, { timeout: 180000, polling: 50 });
    const tv = Date.now() - t0;
    await page.waitForFunction(() => { const c = document.querySelector("#k-card");
      return c?.dataset.full && (c.querySelector(".k-osm")?.checkVisibility() || c.querySelector("[data-no-map]")?.checkVisibility()
        || c.querySelector('[data-part="cities"] .k-none:not([data-pending])')?.checkVisibility()); }, null, { timeout: 240000, polling: 50 }).catch(() => null);
    const tf = Date.now() - t0;
    const h = await page.evaluate(() => Number(document.querySelector('#k-card [data-part="cities"]')?.dataset.heat || 0));
    return { tv, tf, h };
  };
  const w = await one(WARM);
  lines.push(`warm-up ${(w.tv / 1000).toFixed(2)} s to verdict, ${(w.tf / 1000).toFixed(2)} s to full (${WARM})`);
  for (const idea of IDEAS) {
    const r = await one(idea);
    verdict.push(r.tv / 1000); full.push(r.tf / 1000); heat += r.h > 0;
    lines.push(`${(r.tv / 1000).toFixed(2).padStart(6)} s verdict  ${(r.tf / 1000).toFixed(2).padStart(6)} s full  ${String(r.h).padStart(2)} heatmap metros  ${idea}`);
  }
} finally {
  await browser.close();
}
const p95 = rank(verdict, 0.95), ok = verdict.length === 20 && p95 <= 10.0;
lines.push(`${ok ? "PASS" : "FAIL"} test_verdict_speed_cold: p95 ${p95.toFixed(2)} s to the verdict card over 20 never-checked ideas after a redeploy (at most 10.0), `
  + `p50 ${rank(verdict, 0.5).toFixed(2)} s; full card p50 ${rank(full, 0.5).toFixed(2)} s, p95 ${rank(full, 0.95).toFixed(2)} s; ${heat} of 20 full cards with heatmap cities`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(ok ? 0 : 1);
