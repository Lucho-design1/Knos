// test_sample_pr, live: on /check/, "Try a sample pull request" checks drexthealpha/knos-e2e #266 (paid) and #265
// (refused); each shows its verdict, and the paid one its devnet transaction (confirmed) and log line, at 390 and
// 1280 px with no page error. The front door's fourth step opens /check/ with the sample.
//   node scripts/test_sample_pr.mjs <commit sha under test>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_sample_pr.txt`;
const SITE = "https://drexthealpha.github.io/Knos/";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const status = async (sig) => (await (await fetch("https://api.devnet.solana.com", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "getSignatureStatuses", params: [[sig], { searchTransactionHistory: true }] }) })).json()).result?.value?.[0];

const dep = JSON.parse(execFileSync("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"], { encoding: "utf8" }))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const browser = await chromium.launch();
try {
  for (const [w, h] of [[390, 844], [1280, 900]]) {
    const p = await browser.newPage({ viewport: { width: w, height: h } });
    const errors = []; p.on("pageerror", (e) => errors.push(String(e.message).slice(0, 100)));
    await p.goto(SITE + "check/?t=" + Date.now(), { waitUntil: "load" });
    await p.click("#check-sample");
    await p.waitForFunction(() => document.querySelectorAll("#check-sample-out [data-sample] [data-verdict]").length === 2, null, { timeout: 60000 }).catch(() => {});
    await p.waitForTimeout(1500);
    const got = await p.evaluate(() => [...document.querySelectorAll("#check-sample-out [data-sample]")].map((s) => ({ n: s.dataset.sample,
      verdict: s.querySelector("[data-verdict]")?.textContent.trim() || "", knos: s.querySelector("[data-knos]")?.textContent.trim() || "",
      tx: s.querySelector("[data-tx]")?.dataset.tx || null, log: s.querySelector("[data-log]")?.textContent || "" })));
    const tx = got.filter((g) => g.tx);
    let confirmed = 0;
    for (const g of tx) { const st = await status(g.tx).catch(() => null); confirmed += !!st && st.err === null && ["confirmed", "finalized"].includes(st.confirmationStatus); }
    const paid = got.find((g) => g.n === "266"), refused = got.find((g) => g.n === "265");
    ok(got.length === 2 && got.every((g) => g.verdict) && /^Knos: paid/.test(paid?.knos || "") && /does not take the work order/.test(refused?.knos || "")
      && tx.length === 1 && confirmed === 1 && /pr=266\b/.test(paid?.log || "") && errors.length === 0,
      `${w}px: 2 verdicts (${got.map((g) => `#${g.n} "${g.verdict.slice(0, 40)}"`).join("; ")}), Knos "${(paid?.knos || "").slice(0, 30)}" / "${(refused?.knos || "").slice(0, 40)}", ${confirmed} of ${tx.length} devnet transaction confirmed, log "${(paid?.log || "").slice(0, 40)}", ${errors.length} page errors`);
    await p.close();
  }
  const f = await browser.newPage();
  await f.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  const href = await f.evaluate(() => document.getElementById("steps-check")?.href || "");
  ok(href === SITE + "check/#sample", `the front door's fourth step opens ${href}`);
  await f.close();
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_sample_pr: ${fails} check(s) failed` : "PASS test_sample_pr: both verdicts and 1 confirmed devnet transaction at 390 and 1280, 0 page errors");
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
