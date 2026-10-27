// test_check_offline, live: /check/ with api.github.com blocked in Playwright. "Try a sample pull request" shows both
// verdicts (knos-e2e #266 paid, #265 refused) within 2 s from the recording shipped with the site, and #266's devnet
// transaction log line is read live from devnet. A pasted pull request that GitHub refuses (403 with its limit headers)
// shows one reset time, in UTC, and falls back to the labelled recording. At 390 px and 1280 px.
//   node scripts/test_check_offline.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_check_offline.txt`;
const SITE = process.env.KNOS_SITE || "https://drexthealpha.github.io/Knos/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const py = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const render = execFileSync(py, ["-I", process.env.KNOS_RENDER_LATEST], { encoding: "utf8" }).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

const browser = await chromium.launch();
const errors = [];
const RESET = 2000000000;                                   // the limit's reset GitHub would send, seconds since 1970
const utc = new Date(RESET * 1000).toISOString().slice(11, 16) + " UTC";
try {
  for (const [w, scheme] of [[390, "dark"], [1280, "light"]]) {
    // 1. GitHub unreachable: the sample, from the recording
    const cx = await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: scheme });
    let asked = 0;
    await cx.route("https://api.github.com/**", (r) => { asked++; return r.abort(); });
    const p = await cx.newPage();
    p.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    await p.goto(SITE + "check/?t=" + Date.now(), { waitUntil: "load" });
    const t0 = Date.now();
    await p.click("#check-sample");
    const both = await p.waitForFunction(() => ["266", "265"].every((n) => document.querySelector(`[data-sample="${n}"] [data-knos]`)), null, { timeout: 2000, polling: 20 }).then(() => true, () => false);
    const ms = Date.now() - t0;
    const s = await p.evaluate(() => ({ paid: document.querySelector('[data-sample="266"] [data-knos]')?.textContent || "", refused: document.querySelector('[data-sample="265"] [data-knos]')?.textContent || "",
      label: document.querySelector("#check-sample-out [data-recorded]")?.textContent.trim() || "" }));
    ok(both && ms <= 2000 && /^Knos: paid\b/.test(s.paid) && /does not take the work order/.test(s.refused) && /^Recorded \d{4}-\d{2}-\d{2} from GitHub\.$/.test(s.label),
      `${w} ${scheme}: GitHub blocked (${asked} asked), both verdicts in ${ms} ms: "${s.paid.slice(0, 40)}" / "${s.refused.slice(0, 50)}"; "${s.label}"`);
    const log = await p.waitForFunction(() => /:paid .*pr=266/.test(document.querySelector('[data-sample="266"] [data-log]')?.textContent || ""), null, { timeout: 20000 }).then(() => true, () => false);
    ok(log, `${w} ${scheme}: #266's devnet log line, read live: ${(await p.textContent('[data-sample="266"] [data-log]').catch(() => "")).slice(0, 90)}`);
    await cx.close();
    // 2. GitHub's limit on a pasted pull request: one reset time, in UTC, and the recording
    const cy = await browser.newContext({ viewport: { width: w, height: 844 }, colorScheme: scheme });
    await cy.route("https://api.github.com/**", (r) => r.fulfill({ status: 403, contentType: "application/json",
      headers: { "access-control-allow-origin": "*", "access-control-expose-headers": "x-ratelimit-remaining, x-ratelimit-reset", "x-ratelimit-remaining": "0", "x-ratelimit-reset": String(RESET) },
      body: JSON.stringify({ message: "API rate limit exceeded" }) }));
    const q = await cy.newPage();
    q.on("pageerror", (e) => errors.push(`${w}: ${e.message}`));
    for (const [pr, mineRec] of [["https://github.com/drexthealpha/knos-e2e/pull/266", true], ["https://github.com/drexthealpha/Knos/pull/1", false]]) {
      await q.goto(SITE + "check/?t=" + Date.now(), { waitUntil: "load" });
      await q.fill("#check-url", pr); await q.click("#check-run");
      await q.waitForSelector("#check-recorded", { timeout: 10000 }).catch(() => {});
      await q.waitForTimeout(500);
      const r = await q.evaluate(() => ({ text: document.querySelector("main")?.textContent || "", limit: document.querySelector("#check-limit")?.textContent || "",
        recorded: document.querySelector("#check-recorded")?.textContent || "", verdict: !!document.querySelector("#check-result #check-verdict, #check-result [data-sample] [data-knos]") }));
      const times = r.text.match(/\b\d{1,2}:\d{2}(:\d{2})?\s?(AM|PM|UTC)?\b/g) || [];
      ok(times.length === 1 && times[0] === utc && r.limit.includes(utc) && r.verdict && (mineRec ? /^Recorded \d{4}-\d{2}-\d{2} from GitHub:$/.test(r.recorded) : /recorded check/.test(r.recorded)),
        `${w} ${scheme}: pasted ${pr.replace("https://github.com/", "")}, GitHub 403: reset times ${JSON.stringify(times)}; "${r.recorded}"`);
    }
    await cy.close();
  }
} finally {
  await browser.close();
}
ok(errors.length === 0, `page errors: ${errors.length}${errors.length ? ` (${errors.slice(0, 3).join("; ")})` : ""}`);
lines.push(fails ? `FAIL test_check_offline: ${fails} check(s) failed`
  : `PASS test_check_offline: with api.github.com blocked the sample showed both verdicts within 2 s at 390 and 1280, #266's devnet log read live; a pasted pull request refused by GitHub showed one reset time (${utc}) and the labelled recording`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n", { flag: "a" });
process.exit(fails ? 1 : 0);
