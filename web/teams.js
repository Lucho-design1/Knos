// Knos for teams (web/teams/index.html): the prices, the revenue model, the 1B USD arithmetic and a team's dashboard.
// It draws teams_data.json, which `python -m knos.money.business` writes from config/fees.yaml (the one fee config),
// the sourced figures beside it, and a dashboard of `python -m knos.money.teams`. `model` is
// knos.money.business.model, line for line (tests/test_money_teams.py runs both on the same inputs when node is
// installed). textContent only: no HTML is built from data.

const num = (x) => Number(x || 0);
const round2 = (n) => (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);

export const INPUTS = [
  ["verified_merges", "Verified merges a month"],
  ["agent_checks", "Raw agent checks over x402 a month"],
  ["bounty_volume_usd", "Bounties paid a month (USD)"],
  ["task_packages", "Verified task packages sold a month"],
  ["task_package_price_usd", "Price of one task package (USD)"],
];

// fees: the `fees` mapping of config/fees.yaml (teams_data.json carries the four prices; the page passes its numbers)
export function model(inputs, p) {
  const x = inputs || {};
  const month = {
    verified_merge: num(x.verified_merges) * num(p.verified_merge_usd),
    agent_checks: num(x.agent_checks) * num(p.agent_check_usd),
    bounty_fee: num(x.bounty_volume_usd) * num(p.bounty_fee_bps) / 10000,
    task_packages: num(x.task_packages) * num(x.task_package_price_usd) * num(p.task_package_knos_bps) / 10000,
  };
  const total = Object.values(month).reduce((a, b) => a + b, 0);
  const out = {};
  for (const [k, v] of Object.entries(month)) out[k] = round2(v);
  return { month: out, month_total: round2(total), year_total: round2(total * 12) };
}

function cell(doc, tr, text, cls) {
  const td = doc.createElement("td");
  td.textContent = text == null ? "" : String(text);
  if (cls) td.className = cls;
  tr.appendChild(td);
}

function rows(doc, id, list) {
  const body = doc.getElementById(id)?.querySelector("tbody");
  if (!body) return;
  body.textContent = "";
  for (const r of list) {
    const tr = doc.createElement("tr");
    for (const [text, cls] of r) cell(doc, tr, text, cls);
    body.appendChild(tr);
  }
}

function items(doc, id, list) {
  const ul = doc.getElementById(id);
  if (!ul) return;
  ul.textContent = "";
  for (const t of list) {
    const li = doc.createElement("li");
    li.textContent = t;
    ul.appendChild(li);
  }
}

export function renderTeams(doc, d) {
  const set = (id, t) => { const el = doc.getElementById(id); if (el) el.textContent = t; };
  set("t-revenue", `Revenue today: ${d.revenue_today_usd} USD`);
  set("t-why", d.why);
  rows(doc, "t-prices", d.prices.map((p) => [[p.who], [p.line], [p.price], [p.free || ""], [`${p.status}${p.label ? ", " + p.label : ""}`], [p.paid_with]]));
  items(doc, "t-why-now", [d.why_now.claim_vs_ci, d.why_now.merged_anyway, d.why_now.per_1000 + ` (${d.why_now.source})`,
    `${d.why_now.volume} (${d.why_now.volume_source})`, `${d.why_now.labs} (${d.why_now.labs_source})`]);
  set("t-rails", `${d.rails.today}. Later: ${d.rails.later}`);
  items(doc, "t-onboard", d.onboarding);

  const p = d.scale.inputs;
  const params = { verified_merge_usd: p.verified_merge_usd, agent_check_usd: p.agent_check_usd, bounty_fee_bps: p.bounty_fee_bps,
    task_package_knos_bps: p.task_package_knos_bps };
  set("t-model-label", d.model.label);
  const form = doc.getElementById("t-inputs");
  const draw = () => {
    const x = {};
    for (const [k] of INPUTS) x[k] = num(doc.getElementById("t-in-" + k)?.value);
    const m = model(x, params);
    rows(doc, "t-model", [...Object.entries(m.month).map(([k, v]) => [[k], [v, "num"]]), [["a month"], [m.month_total, "num"]], [["a year"], [m.year_total, "num"]]]);
  };
  if (form) {
    form.textContent = "";
    for (const [k, label] of INPUTS) {
      const l = doc.createElement("label");
      l.textContent = label + " ";
      const i = doc.createElement("input");
      i.type = "number"; i.min = "0"; i.value = "0"; i.id = "t-in-" + k;
      i.addEventListener("input", draw);
      l.appendChild(i); form.appendChild(l);
    }
  }
  draw();

  const b = d.scale;
  set("t-scale-label", b.label);
  const a = b.each_line_alone;
  items(doc, "t-scale", [
    `verified merges alone: ${num(a.verified_merges_a_month).toLocaleString("en-US")} a month (${a.verified_merges_share_of_github_merges} of GitHub's merged pull requests)`,
    `agent checks alone: ${num(a.agent_checks_a_month).toLocaleString("en-US")} a month`,
    `bounty fee alone: ${num(a.bounty_volume_usd_a_year).toLocaleString("en-US")} USD of bounties a year`,
    `task packages alone: ${num(a.task_packages_a_year_at_2000_usd).toLocaleString("en-US")} (at 2,000 USD) to ${num(a.task_packages_a_year_at_200_usd).toLocaleString("en-US")} (at 200 USD) a year`,
  ]);
  rows(doc, "t-github", b.share_of_github_merges_at_starting_price.map((r) => [[r.share_pct + "%"], [num(r.verified_merges_a_month).toLocaleString("en-US"), "num"], [num(r.usd_a_year).toLocaleString("en-US"), "num"]]));
  set("t-reading", b.reading);
  items(doc, "t-sources", Object.values(d.sources).map((s) => `${s.said}: ${s.source}`));

  const t = d.team;
  if (!t) { set("t-dash-none", "No team dashboard in this data file."); return; }
  set("t-dash-team", `${t.team}${t.labels && t.labels.length ? " (" + t.labels.join(", ") + ")" : ""}`);
  rows(doc, "t-dash", Object.entries(t.totals).map(([k, v]) => [[k.replaceAll("_", " ")], [v, "num"]]));
  set("t-saved", `Failing merges blocked: ${t.money_saved.failing_merges_blocked}. ${t.money_saved.means}`);
  const pf = t.paid_and_final;
  set("t-final", pf.n ? `Paid and final in ${pf.p50_ms} ms (p50 of ${pf.n} devnet transactions; p95 ${pf.p95_ms} ms). ${pf.label}.` : "No devnet transaction in this record.");
  rows(doc, "t-invoice", t.invoice.lines.map((l) => [[l.at], [l.agent], [l.line], [l.usd, "num"], [l.evidence || ""], [l.sig || ""]]));
  set("t-due", `Due: ${t.invoice.due_usd} USD (test money). ${t.invoice.pay_with}.`);
}
