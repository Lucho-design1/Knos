// test_usage_trend_live: on the live front door (Pages at the commit given), the usage counter shows no static numbers:
// the exact line "<n> ideas checked this week, up from <m> last week" when the app's outside counts give one (n > m and
// n >= 10), else no counter at all. The 3 trend unit tests are read from CI on that commit (the "tests" workflow).
//
//   node scripts/test_usage_trend_live.mjs <Pages commit sha> [CI commit sha]
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

const SHA = process.argv[2], CI = process.argv[3] || SHA;     // CI is read on the newest commit (a push cancels the older runs)
const OUT = `${process.env.KNOS_WORLD || "C:/Users/zulab/knos-v1-private/v0328/world"}/test_usage_trend_live.txt`;
const lines = [];
let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const gh = (path) => JSON.parse(execFileSync("gh", ["api", path], { encoding: "utf8" }));

const dep = gh("repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1")[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (the commit under test ${SHA.slice(0, 7)})`);
const u = await (await fetch("https://knos.onrender.com/api/usage")).json();
const t = u.trend || {};
lines.push(`live outside counts: this week n=${t.this_week}, last week m=${t.last_week}; line: ${JSON.stringify(t.line)}`);
const browser = await chromium.launch();
let shown;
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto("https://drexthealpha.github.io/Knos/?t=" + Date.now(), { waitUntil: "load" });
  await page.mouse.move(300, 300); await page.mouse.wheel(0, 600);           // the reader's first move, then Paid on proof in view,
  await page.locator("#paid-on-proof").scrollIntoViewIfNeeded().catch(() => null);   // asks the app again
  await page.waitForSelector("#k-usage[data-live]", { state: "attached", timeout: 90000 }).catch(() => null);
  await page.waitForTimeout(1500);
  shown = await page.evaluate(() => { const e = document.getElementById("k-usage");
    return { exists: !!e, live: e?.dataset.live === "1", visible: !!e && !e.hidden && e.checkVisibility(), text: e?.textContent.trim() || "",
      page: document.body.innerText }; });
} finally {
  await browser.close();
}
ok(shown.live, "the counter was asked again from the app after load");
ok(!/demand checks ·|Ready briefs since|payment program transactions/i.test(shown.page), "the rendered page holds none of the old static usage numbers");
if (t.line) ok(shown.visible && shown.text === t.line, `the exact trend line with the live numbers: ${JSON.stringify(shown.text)}`);
else ok(!shown.visible && shown.text === "", "no counter (the live outside counts do not meet n > m and n >= 10)");
const runs = gh(`repos/drexthealpha/Knos/actions/runs?head_sha=${CI}`).workflow_runs || [];
const tests = runs.filter((r) => /tests/i.test(r.name));
lines.push(`CI on ${CI.slice(0, 7)}: ${runs.map((r) => `${r.name} ${r.status}/${r.conclusion}`).join("; ")}`);
ok(tests.length > 0 && tests.every((r) => r.conclusion === "success"), `the tests workflow on ${CI.slice(0, 7)} succeeded (it runs apps/wanted/tests/test_usage_trend.py)`);
lines.push(fails ? `FAIL test_usage_trend_live: ${fails} check(s) failed` :
  `PASS test_usage_trend_live: ${t.line ? `the trend line shows exactly (n=${t.this_week}, m=${t.last_week})` : `no counter shown (live n=${t.this_week}, m=${t.last_week})`}, no static usage numbers, CI tests green`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
