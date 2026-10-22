// Screenshots of the two front doors at a phone and a laptop width, signed out: node scripts/shots.mjs <out dir>
import { chromium } from "playwright";

const OUT = process.argv[2] || ".";
const PAGES = { site: process.env.SITE_URL || "https://drexthealpha.github.io/Knos/", app: process.env.APP_URL || "https://knos.onrender.com/" };
const browser = await chromium.launch();
for (const [name, url] of Object.entries(PAGES)) {
  for (const [w, h] of [[375, 812], [1280, 800]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(url, { waitUntil: "load", timeout: 90000 });
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${OUT}/${name}-${w}.png` });
    await page.close();
  }
}
await browser.close();
console.log("wrote 4 screenshots to " + OUT);
