// test_small_fixes, live: every N6 item. The SSO button names the test identity provider; the card's limit notice and
// its Claude alone fold sit inside the card's padding; the calls list shows the idea's own words (no "familie"); /r/<id>
// has a Print button hidden in print; /qloo-safe-use links no trace without its hash; Render's /quality/ goes to the
// front door's; pricing works one payout through with its fee.
//   node scripts/test_small_fixes.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_small_fixes.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const SSO = "Try SSO with a test identity provider (opens mocksaml.com)";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const cards = JSON.parse(readFileSync(REC, "utf8")).cards;
const browser = await chromium.launch();
const errors = [];
try {
  const p = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  p.on("pageerror", (e) => errors.push(e.message));
  // 1. the SSO button
  await p.goto(`${API}/companies?t=${Date.now()}`, { waitUntil: "load" });
  ok((await p.textContent("#co-sso").catch(() => "")).trim() === SSO, `/companies: the SSO button reads "${SSO}"`);
  // 2 and 3. the card's padding and its words
  await p.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  await p.fill("#k-q", "an AI recipe planner for families"); await p.click("#k-go");
  await p.waitForSelector("#k-card > .k-card [data-qloo-down]", { timeout: 60000 }).catch(() => {});
  await p.waitForFunction(() => !document.querySelector("#k-card > .k-card details[data-claude]")?.hidden, null, { timeout: 15000 }).catch(() => {});
  const c = await p.evaluate(() => { const k = document.querySelector("#k-card > .k-card"), kl = k.getBoundingClientRect().left;
    const inset = (el) => el && el.checkVisibility() ? Math.round(el.getBoundingClientRect().left - kl) : null;
    return { notice: inset(k.querySelector("[data-qloo-down]")), claude: inset(k.querySelector("details[data-claude] > summary")),
      calls: k.querySelector('[data-part="calls"]')?.textContent || "" }; });
  ok(c.notice >= 16 && c.claude >= 16, `the limit notice and the Claude alone fold sit inside the card: ${c.notice} px and ${c.claude} px from its edge`);
  ok(!/familie\b/.test(c.calls) && /families/.test(c.calls), `the calls list shows "families", ${(c.calls.match(/familie\b/g) || []).length} "familie"`);
  // 4. Print on /r/<id>, hidden in print
  const id = Object.values(cards)[0].hash.slice(0, 16);
  await p.goto(`${API}/r/${id}?t=${Date.now()}`, { waitUntil: "load" });
  const screen = await p.isVisible("#r-print");
  await p.emulateMedia({ media: "print" });
  const printed = await p.isVisible("#r-print");
  await p.emulateMedia({ media: "screen" });
  ok(screen && !printed, `/r/${id}: Print ${screen ? "shown" : "missing"} on screen, ${printed ? "shown" : "hidden"} in print`);
  // 5. no trace link without its hash
  await p.goto(`${API}/qloo-safe-use?t=${Date.now()}`, { waitUntil: "load" });
  const bare = await p.evaluate(() => [...document.querySelectorAll("a[href]")].filter((a) => /trace\.html/.test(a.href) && !/[?&]hash=[0-9a-f]/.test(a.href)).map((a) => a.href));
  ok(bare.length === 0, `/qloo-safe-use: ${bare.length} trace links without a hash`);
} finally {
  await browser.close();
}
// 6. /quality/
const q = await fetch(`${API}/quality/`, { redirect: "manual" });
ok(q.status === 301 && q.headers.get("location") === "https://drexthealpha.github.io/Knos/quality/" && (await fetch(q.headers.get("location") || "x").catch(() => ({ status: 0 }))).status === 200,
  `Render /quality/: ${q.status} to ${q.headers.get("location")}`);
// 7. pricing's worked example
const pr = await (await fetch(SITE + "pricing.html?t=" + Date.now())).text();
const ex = (pr.match(/<p class="p-n" data-example>(.*?)<\/p>/) || [])[1] || "";
ok(/25\.00 test USDC/.test(ex) && /0\.075 fee/.test(ex) && /25\.075/.test(ex) && /solver receives 25\.00/.test(ex), `pricing: "${ex}"`);
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_small_fixes: ${fails} check(s) failed` : "PASS test_small_fixes: the SSO label, the card's padding, the idea's own words in the calls, Print on /r/, no bare trace link, /quality/ redirected and the worked payout, each checked live");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
