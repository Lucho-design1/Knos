// test_qloo_depth, live: the guard's unit tests pass and the guard finds 0 invalid parameters in the 6 recorded cards;
// How we test publishes "What each Qloo signal changes"; on each of the 6 recorded chips, asked in the front door's
// box, "Without Qloo" shows no city, no target and pre-orders closed, offline too; every calls row holds its endpoint,
// parameters, milliseconds, cached or live, and the part it set; "because" and the trend line show; /status/qloo
// answers 200.
//   node scripts/test_qloo_depth.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

const [SHA, REC] = process.argv.slice(2);
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_qloo_depth.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const PY = process.env.KNOS_PY || ".venv/Scripts/python.exe";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const sh = (cmd, args, opts = {}) => { try { return { out: execFileSync(cmd, args, { encoding: "utf8", maxBuffer: 1 << 26, ...opts }), code: 0 }; } catch (e) { return { out: String(e.stdout || ""), code: e.status || 1 }; } };

const dep = JSON.parse(sh("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"]).out)[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const render = sh(PY, ["-I", process.env.KNOS_RENDER_LATEST]).out.trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);

// (a) the guard: its unit tests, then the guard over every call the 6 recordings hold
const unit = sh(PY, ["-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_qloo_depth.py"], { cwd: "apps/wanted" });
const passed = Number((/(\d+) passed/.exec(unit.out) || [0, 0])[1]);
ok(unit.code === 0 && passed >= 4, `guard unit tests: ${passed} passed`);
const guard = sh(PY, ["-I", "-c", `import json,sys; sys.path.insert(0,'apps/wanted')
from knos_wanted import qloo_guard
cards=json.load(open(sys.argv[1],encoding='utf-8'))['cards']; n=bad=0; said={}
for c in cards.values():
    for call in c.get('calls') or []:
        n+=1; p=qloo_guard.problems(call['call'].split(' ',1)[-1], call.get('params') or {})
        bad+=bool(p)
        for x in p: said[x]=said.get(x,0)+1
print(json.dumps({'calls':n,'invalid':bad,'said':said}))`, REC]);
const g = JSON.parse(guard.out || "{}");
ok(g.calls > 0 && g.invalid === 0, `guard over the 6 recordings: ${g.invalid} invalid of ${g.calls} calls ${JSON.stringify(g.said || {})}`);

const ideas = Object.keys(JSON.parse(readFileSync(REC, "utf8")).cards);
const doc = JSON.parse(readFileSync("docs/reference/qloo_ablation.json", "utf8"));
const browser = await chromium.launch();
let chipsOk = 0, rows = 0, rowsOk = 0, because = 0, trend = 0;
try {
  // (b) the ablation table, published
  const how = await (await browser.newPage()).goto(SITE + "how-we-test.html?t=" + Date.now());
  const page0 = await how.text();
  const sec = (page0.split('id="ablation"')[1] || "").split("</section>")[0];
  ok(/What each Qloo signal changes/.test(sec) && (sec.match(/<tr><td>/g) || []).length === doc.rows.length,
    `How we test publishes "What each Qloo signal changes": ${(sec.match(/<tr><td>/g) || []).length} rows (JSON ${doc.rows.length})`);
  // (c), (d), (e) on each recorded chip
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  for (const idea of ideas) {
    await page.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
    await page.fill("#k-q", idea);
    await page.click("#k-go");
    let got = { err: "" };
    try {
      await page.waitForSelector('#k-card .k-card [data-without][aria-pressed="false"]', { timeout: 180000 });
      await page.waitForTimeout(500);
      got = await page.evaluate(() => {
        const card = document.querySelector("#k-card .k-card");
        return { rows: [...card.querySelectorAll('[data-part="calls"] li')].map((li) => li.textContent.replace(/\s+/g, " ").trim()),
          because: card.querySelectorAll("[data-because]").length, trend: !!card.querySelector('[data-part="trend"]'), err: "" };
      });
      await ctx.setOffline(true);
      await page.click('#k-card [data-without][aria-pressed="false"]');
      const w = await page.evaluate(() => {
        const c = document.querySelector("#k-card [data-without-qloo]");
        return c ? { text: c.textContent, terms: !!c.querySelector(".k-terms"), cities: c.querySelectorAll("ol li").length } : null; });
      await page.click('#k-card [data-without][aria-pressed="true"]');
      const back = await page.evaluate(() => !!document.querySelector('#k-card .k-card [data-without][aria-pressed="false"]'));
      await ctx.setOffline(false);
      got.without = !!w && /no launch city and no pre-order target, so pre-orders cannot open/.test(w.text) && !w.terms && w.cities === 0 && back;
    } catch (e) {
      await ctx.setOffline(false);
      got.err = String(e.message || e).split("\n")[0].slice(0, 80);
    }
    // a row: "#n GET /path params · ms ms · cached|live · the part it set"
    const good = (got.rows || []).filter((r) => /^#\d+ (GET|POST) \/\S+ \S.* · \d+ ms · (cached|live)( · failed)? · \S/.test(r)).length;
    rows += (got.rows || []).length; rowsOk += good; because += got.because > 0; trend += !!got.trend; chipsOk += !!got.without;
    lines.push(`${got.without ? "ok  " : "FAIL"} ${idea.slice(0, 40).padEnd(40)} Without Qloo offline ${got.without ? "closes pre-orders" : "no"}, calls ${good}/${(got.rows || []).length} with 5 fields, because ${got.because || 0}, trend ${got.trend ? "yes" : "no"}${got.err ? ` (${got.err})` : ""}`);
  }
  ok(chipsOk === ideas.length, `Without Qloo works offline on ${chipsOk} of ${ideas.length} recorded chips`);
  ok(rows > 0 && rowsOk === rows, `calls rows with endpoint, params, ms, cached or live, and the part: ${rowsOk} of ${rows}`);
  ok(because > 0 && trend > 0, `"because" on ${because} chips, the trend line on ${trend}`);
} finally {
  await browser.close();
}
// (f) /status/qloo
const st = await fetch(API + "/status/qloo");
const body = await st.text();
ok(st.status === 200 && /Qloo/.test(body), `/status/qloo answers ${st.status}`);
lines.push(fails ? `FAIL test_qloo_depth: ${fails} check(s) failed; guard ${g.invalid} invalid of ${g.calls}, switch ${chipsOk}/${ideas.length}, calls rows ${rowsOk}/${rows}` :
  `PASS test_qloo_depth: guard 0 invalid of ${g.calls}, ablation ${doc.rows.length} rows, switch ${chipsOk}/${ideas.length} offline, calls rows ${rowsOk}/${rows}, /status/qloo 200`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
