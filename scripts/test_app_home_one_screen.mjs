// test_app_home_one_screen, live: the app's home (https://knos.onrender.com/) is the front door's hero and result card,
// and its rendered text names no passkey wallet, company single sign-on or accounting export ("passkey", "SSO",
// "SAML", "Xero", "QuickBooks"). "More" holds at most 7 items and the top navigation at most 6. Every item taken out of
// "More" still answers at its own address (HTTP 200); each is listed with its URL.
//
//   node scripts/test_app_home_one_screen.mjs
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const APP = "https://knos.onrender.com/", FRONT = "https://drexthealpha.github.io/Knos/";
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_app_home_one_screen.txt`;
const WORDS = ["passkey", "SSO", "SAML", "Xero", "QuickBooks"];
// taken out of "More" (web/brand/bar.html) on 25 Oct 2026, each still at its own address
const REMOVED = [["How we verify", `${FRONT}#verify`], ["Back a product", `${APP}#buy`], ["Fund a milestone", `${APP}#fund`],
  ["Open work", `${APP}#contribute`], ["Make", `${APP}#make`], ["Teams", `${APP}#teams`], ["Agents", `${APP}#agents`],
  ["Invite", `${APP}invite`], ["Demo", `${FRONT}#demo`], ["Install", `${FRONT}#install`], ["Records", `${FRONT}#records`],
  ["Numbers", `${FRONT}#network`]];
const lines = [];
let fails = 0;
const ok = (c, what, got) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}${got === undefined ? "" : ` ${JSON.stringify(got).slice(0, 240)}`}`); if (!c) fails++; };
const browser = await chromium.launch();
try {
  const read = async (url) => {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
    await page.goto(url, { waitUntil: "load", timeout: 120000 });
    await page.waitForTimeout(1500);
    const g = await page.evaluate(() => {
      const nav = document.querySelector("header nav#nav");
      return { text: document.body.innerText, h1: document.querySelector("#k-hero h1")?.textContent.trim(),
        chips: [...document.querySelectorAll("#k-hero .k-chip[data-q]")].map((c) => c.dataset.q), input: !!document.querySelector("#k-hero #k-q"),
        card: !!document.querySelector("#k-hero #k-card"), top: [...nav.children].map((e) => e.matches(".more") ? "More" : e.textContent.trim()),
        more: [...document.querySelectorAll("#more-list a")].map((a) => a.textContent.trim()) };
    });
    await page.context().close();
    return g;
  };
  const app = await read(APP), front = await read(FRONT);
  const hits = WORDS.map((w) => [w, (app.text.match(new RegExp(`\\b${w}\\b`, "gi")) || []).length]).filter(([, n]) => n);
  ok(hits.length === 0, `app home rendered text: ${hits.reduce((n, [, k]) => n + k, 0)} of ${WORDS.join(", ")}`, hits);
  ok(app.h1 === front.h1 && app.input && app.card && JSON.stringify(app.chips) === JSON.stringify(front.chips),
     "the app home shows the front door's hero and result card", { h1: app.h1, chips: app.chips.length });
  ok(app.top.length <= 6, `top navigation: ${app.top.length} items (at most 6)`, app.top);
  ok(app.more.length <= 7, `"More": ${app.more.length} items (at most 7)`, app.more);
  let broken = 0;
  for (const [name, url] of REMOVED) {
    const r = await fetch(url, { redirect: "follow" }).catch(() => null);
    const code = r ? r.status : 0;
    broken += code !== 200;
    lines.push(`${code === 200 ? "ok  " : "FAIL"} removed from "More": ${name} -> ${url} (HTTP ${code})`);
  }
  if (broken) fails++;
  ok(broken === 0, `${broken} broken URLs among the ${REMOVED.length} removed items`);
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_app_home_one_screen: ${fails} check(s) failed` : `PASS test_app_home_one_screen: 0 wallet, sign-on or accounting words on the app home, top 6 or fewer, "More" 7 or fewer, ${REMOVED.length} removed items all HTTP 200`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
