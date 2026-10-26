// test_share_result, live: each of the 6 recorded sample chips has a permanent page /r/<id> on the app that answers 200
// after the redeploy; its QR code reads back to its own address (read by knos_wanted.qr's reader from the drawn SVG);
// its print preview is one page; the front door's card links it; and the 4 states that are not a full answer each say
// one plain sentence (error and thin from the live app; empty and outage drawn by the same code from SYNTHETIC
// reports, since no recorded card is in those states), with a screenshot of each.
//   node scripts/test_share_result.mjs <commit sha under test> <private recordings file>
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [SHA, REC] = process.argv.slice(2);
const WORLD = process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`;
const OUT = `${WORLD}/test_share_result.txt`;
const SITE = "https://drexthealpha.github.io/Knos/", API = "https://knos.onrender.com";
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const PY = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const run = (cmd, args, input) => { try { return execFileSync(cmd, args, { encoding: "utf8", maxBuffer: 1 << 26, cwd: ROOT, input }); } catch (e) { return String(e.stdout || "") + String(e.stderr || ""); } };
const READ = `import re,sys; sys.path.insert(0,'apps/wanted')
from knos_wanted import qr
s=sys.stdin.read(); n=int(re.search(r'data-modules="(\\d+)"',s)[1]); px=int(re.search(r'data-px="(\\d+)"',s)[1]); q=int(re.search(r'data-quiet="(\\d+)"',s)[1])
g=[[False]*n for _ in range(n)]
for x,y in re.findall(r'M(\\d+),(\\d+)h',s): g[int(y)//px-q][int(x)//px-q]=True
print(qr.read(g))`;

const dep = JSON.parse(run("gh", ["api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"]))[0];
ok(dep && dep.sha === SHA, `Pages deployed at ${dep && dep.sha.slice(0, 7)} (commit under test ${SHA.slice(0, 7)})`);
const render = run(PY, ["-I", process.env.KNOS_RENDER_LATEST]).trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]}): its boot read the recordings again`);

const cards = JSON.parse(readFileSync(REC, "utf8")).cards;
const browser = await chromium.launch();
let pages200 = 0, decoded = 0, onePage = 0;
const states = {};
try {
  for (const [idea, c] of Object.entries(cards)) {
    const id = c.hash.slice(0, 16), url = `${API}/r/${id}`;
    const r = await fetch(url);
    const body = await r.text();
    pages200 += r.status === 200;
    const svg = (/<svg[^]*?<\/svg>/.exec(body) || [""])[0];
    const said = run(PY, ["-I", "-c", READ], svg).trim();
    decoded += said === url;
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await page.goto(url, { waitUntil: "load" });
    const st = await page.evaluate(() => document.querySelector("[data-state]")?.dataset.state || "full");
    states[st] ||= url;
    const pdf = await page.pdf({ format: "A4", printBackground: false });
    const n = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
    onePage += n === 1;
    await page.close();
    lines.push(`${r.status === 200 && said === url && n === 1 ? "ok  " : "FAIL"} ${idea.slice(0, 38).padEnd(38)} /r/${id} ${r.status}, QR reads ${said === url ? "its address" : JSON.stringify(said.slice(0, 60))}, print ${n} page(s), ${st}`);
  }
  ok(pages200 === 6, `/r/<id> after the redeploy: ${pages200} of 6 answer 200`);
  ok(decoded === 6, `QR codes read back to their page's address: ${decoded} of 6`);
  ok(onePage === 6, `print preview on one A4 page: ${onePage} of 6`);
  // the front door's card links its page
  const front = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const [idea0, c0] = Object.entries(cards)[0];
  await front.goto(SITE + "?t=" + Date.now(), { waitUntil: "load" });
  await front.fill("#k-q", idea0); await front.click("#k-go");
  const href = await front.waitForSelector("#k-card [data-share]", { timeout: 180000 }).then((e) => e.getAttribute("href")).catch(() => "");
  ok(href === `${API}/r/${c0.hash.slice(0, 16)}`, `the front door's card links its page: ${href}`);
  await front.close();
  // the 4 states, each one sentence, each a screenshot
  const shot = async (name, go) => {
    const p = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await go(p);
    const s = await p.evaluate(() => { const e = document.querySelector("[data-state]"); return e ? [e.dataset.state, e.textContent.trim()] : null; });
    await p.screenshot({ path: `${WORLD}/test_share_result_${name}.png`, fullPage: true });
    await p.close();
    const one = !!s && s[0] === name && s[1].endsWith(".") && (s[1].match(/\./g) || []).length === 1;
    ok(one, `${name}: one sentence, "${s ? s[1] : "none"}" (screenshot test_share_result_${name}.png)`);
  };
  await shot("error", (p) => p.goto(`${API}/r/0000000000000000`, { waitUntil: "load" }));
  if (states.thin) await shot("thin", (p) => p.goto(states.thin, { waitUntil: "load" }));
  const synth = JSON.parse(run(PY, ["-I", "-c", `import json,sys; sys.path.insert(0,'apps/wanted')
from knos_wanted import result_page as R
base={'idea':'SYNTHETIC test idea','hash':'0'*64,'made':'2026-10-26T00:00:00Z','decision':{'verdict':'CANNOT_DECIDE'},'calls':[],'cities':[],'where':[]}
out={'empty':R.page({**base,'matches':[]},'https://knos.example/r/'+'0'*16,'0'*16),
     'outage':R.page({**base,'matches':[{'id':'x'}],'stale':{'code':429}},'https://knos.example/r/'+'0'*16,'0'*16)}
if 'thin' not in sys.argv: out['thin']=R.page({**base,'matches':[{'id':'x'}]},'https://knos.example/r/'+'0'*16,'0'*16)
print(json.dumps(out))`, ...(states.thin ? ["thin"] : [])]) || "{}");
  for (const [name, htmlText] of Object.entries(synth)) await shot(name, (p) => p.setContent(htmlText, { waitUntil: "load" }));
} finally {
  await browser.close();
}
lines.push(fails ? `FAIL test_share_result: ${fails} check(s) failed` :
  `PASS test_share_result: 6 of 6 /r/ pages 200 after the redeploy, 6 of 6 QR codes read back, 6 of 6 print on one page, 4 states each one sentence`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
