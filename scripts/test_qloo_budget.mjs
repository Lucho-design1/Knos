// test_qloo_budget: the unit tests cover both refusals (under 2,000 left in Qloo's month, past 1,500 calls on the
// day) and the kept headers; live, after one check of an idea with no recording (this run's one Qloo request, made by
// the app), /status/qloo shows the month's calls left and when it resets, from Qloo's own headers.
//   node scripts/test_qloo_budget.mjs <commit sha under test>
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SHA = process.argv[2];
const OUT = `${process.env.KNOS_WORLD || `${process.env.KNOS_PRIVATE_DIR || "."}/v0328/world`}/test_qloo_budget.txt`;
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const PY = process.env.KNOS_PY || fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
const API = "https://knos.onrender.com";
const lines = []; let fails = 0;
const ok = (c, what) => { lines.push(`${c ? "ok  " : "FAIL"} ${what}`); if (!c) fails++; };
const run = (cmd, args, cwd = ROOT) => { try { return { out: execFileSync(cmd, args, { encoding: "utf8", cwd, env: { ...process.env, KNOS_FULL_TEST_OUTPUT: "1" } }), code: 0 }; }
  catch (e) { return { out: String(e.stdout || "") + String(e.stderr || ""), code: e.status || 1 }; } };

const render = run(PY, ["-I", process.env.KNOS_RENDER_LATEST]).out.trim().split(/\s+/);
ok(render[1] === "live" && SHA.startsWith(render[2]), `Render live at ${render[2]} (${render[1]})`);
const unit = run(PY, ["-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_qloo_budget.py"], ROOT + "apps/wanted");
ok(unit.code === 0 && /4 passed/.test(unit.out), `unit tests (both refusals, the kept headers): ${(unit.out.trim().split("\n").at(-1) || "").trim()}`);
let d = await (await fetch(`${API}/api/qloo/status?t=${Date.now()}`)).json();
if (d.month_left == null) {
  // one check of an idea with no recording: the app asks Qloo (or is held by its pause) and keeps what Qloo's answer says
  await fetch(`${API}/api/check`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea: "a ceramic pour-over coffee dripper for travelers", stage: "verdict" }) }).catch(() => null);
  d = await (await fetch(`${API}/api/qloo/status?t=${Date.now()}`)).json();
}
const page = await (await fetch(`${API}/status/qloo?t=${Date.now()}`)).text();
const row = (/<dt>Qloo's month, calls left<\/dt><dd>([^<]*)<\/dd>/.exec(page) || [])[1] || "";
ok(d.month_left != null && d.month_reset != null && row.includes(String(d.month_left)) && row.includes(String(d.month_reset)),
  `/status/qloo shows Qloo's month: "${row}" (read ${d.limits_read || "never"}; held ${d.held_s} s)`);
lines.push(fails ? `FAIL test_qloo_budget: ${fails} check(s) failed` : `PASS test_qloo_budget: both refusals unit-tested; /status/qloo shows ${d.month_left} calls left, resets ${d.month_reset}`);
console.log(lines.join("\n"));
writeFileSync(OUT, lines.join("\n") + "\n");
process.exit(fails ? 1 : 0);
