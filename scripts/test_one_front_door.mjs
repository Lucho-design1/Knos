// test_one_front_door, live: the Pages root (raw HTML, scripts removed) is the demand check alone; the app's home holds
// none of the money or company tools and /paid holds them; /check/ checks a real pull request to a visible verdict
// within 90 s; every old address of the root answers 200 or is sent on; the descriptions are docs/facts.json's.
//   node scripts/test_one_front_door.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_one_front_door.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", APP = "https://knos.onrender.com";
const PR = "https://github.com/drexthealpha/knos-e2e/pull/266";
const MISSION = "See who wants your product, and where, before you build it";
const MOVED = ["passkey", "SAML", "SSO", "Squads", "Xero", "QuickBooks", "devnet SOL"];
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const raw = (h) => h.replace(/<script\b[\s\S]*?<\/script>/gi, " ");
const text = async (u) => { const r = await fetch(u + (u.includes("?") ? "&" : "?") + "t=" + Date.now(), { redirect: "manual" }); return [r.status, await r.text()]; };
const gh = (path) => JSON.parse(execFileSync("gh", ["api", path], { encoding: "utf8" }));

const dep = gh("repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1")[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (the commit under test ${SHA.slice(0, 7)})`);
const [, root] = await text(SITE), page = raw(root);
const h1 = [...page.matchAll(/<h1\b[^>]*>([\s\S]*?)<\/h1>/g)].map((m) => m[1].replace(/<[^>]+>/g, "").trim());
ok(JSON.stringify(h1) === JSON.stringify([MISSION]), `root: 1 h1, "${h1.join(" | ")}"`);
const chips = (page.match(/class="k-chip"/g) || []).length, steps = ((page.match(/<ol class="k-step-list">([\s\S]*?)<\/ol>/) || [])[1] || "").match(/<li\b/g) || [];
ok(page.includes('id="k-q"') && chips === 8 && page.includes('id="k-card"') && steps.length === 4 && page.includes("See it in 3 clicks"),
  `root: the box, ${chips} chips, the card's place, ${steps.length} steps, the 3 clicks`);
const gone = ['id="view-check"', 'id="front-door"', "Check an AI agent's pull request", 'id="view-records"', 'id="hero-fact"'].filter((g) => page.includes(g));
ok(gone.length === 0, `root: no pull-request checker and no other page in it ${JSON.stringify(gone)}`);
ok(/<a href="\.\/check\/" id="steps-check">Check a pull request<\/a>/.test(page), "root: Paid on proof's \"Check a pull request\" goes to /check/");
const [hs, home] = await text(APP + "/"), [ps, paid] = await text(APP + "/paid");
const count = (h) => Object.fromEntries(MOVED.map((w) => [w, (raw(h).match(new RegExp(`\\b${w.replace(/ /g, "\\s+")}\\b`, "gi")) || []).length]));
ok(hs === 200 && Object.values(count(home)).every((n) => n === 0), `app home ${APP}/ (raw, scripts removed): ${JSON.stringify(count(home))}`);
ok(ps === 200 && MOVED.every((w) => count(paid)[w] > 0), `the moved sections are at ${APP}/paid: ${JSON.stringify(count(paid))}`);

const browser = await chromium.launch();
try {
  const p = await browser.newPage();
  await p.goto(SITE + "check/?t=" + Date.now(), { waitUntil: "domcontentloaded" });
  await p.fill("#check-url", PR);
  const t0 = Date.now();
  await p.click("#check-run");
  const seen = await p.waitForFunction(() => { const v = document.getElementById("check-verdict"); return v && v.checkVisibility() && v.textContent.trim(); }, null, { timeout: 90000 }).then(() => true).catch(() => false);
  const said = seen ? (await p.textContent("#check-verdict")).trim() : "";
  ok(seen, `/check/: ${PR} checked to a visible verdict in ${((Date.now() - t0) / 1000).toFixed(1)} s: "${said.slice(0, 120)}"`);
  for (const [hash, want] of [["#check", "/Knos/check/"], ["#check=drexthealpha/knos-e2e/266", "/Knos/check/"], ["#check-a-pull-request", "/Knos/check/"],
                              ["#records", "/Knos/app.html"], ["#pricing", "/Knos/app.html"], ["#fund", "/Knos/app.html"], ["#network", "/Knos/app.html"], ["#home", "/Knos/"]]) {
    const r = await p.goto(SITE + hash, { waitUntil: "domcontentloaded" });
    await p.waitForTimeout(1200);
    const u = new URL(p.url());
    ok(r && r.status() === 200 && u.pathname === want, `old address ${hash}: answered ${r && r.status()}, now at ${u.pathname}${u.hash}`);
  }
} finally {
  await browser.close();
}
const facts = JSON.parse(readFileSync(new URL("../docs/facts.json", import.meta.url), "utf8")), said = [facts.sentence, facts.registry_sentence];
const server = JSON.parse(readFileSync(new URL("../server.json", import.meta.url), "utf8")).description;
const npm = JSON.parse(readFileSync(new URL("../sdk/settle/package.json", import.meta.url), "utf8")).description;
const pyproject = /^description = "(.*)"$/m.exec(readFileSync(new URL("../pyproject.toml", import.meta.url), "utf8"))[1];
const lead = /\*\*(.+?)\*\*/.exec(readFileSync(new URL("../README.md", import.meta.url), "utf8").split("</h1>")[1])[1];
ok([server, npm, pyproject, lead].every((d) => said.includes(d)), `descriptions (server.json, npm, PyPI's pyproject, README's lead) are facts.json's sentences`);
lines.push(fails ? `FAIL test_one_front_door: ${fails} check(s) failed` :
  `PASS test_one_front_door: root holds 1 h1, 8 chips, 4 steps and nothing else; app home 0 of ${MOVED.length} moved words; /check/ verdict within 90 s; old addresses 200 or sent on`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
