"""The live panel: tokens, latency, cost per verified improvement, cheats caught. One JSON file and one static HTML page
that carries the same JSON inside it (opens from disk, no server, no script from anywhere else).

Every number comes from the run: the model calls' usage and timing, Tavily's credits, the referee's decisions. In MOCK
mode the token counts are estimates the mock made and the latency is the mock's, so the page says MOCK on every such
number. A count that is zero is printed as 0; a ratio with nothing to divide by is printed as "none".
"""
from __future__ import annotations

import json
from pathlib import Path

from . import sources


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def metrics(replies: list, searches: list, *, kept: int, graduated: bool, refused_ar: int, refused_self: int,
            rules_accepted: int, rules_proposed: int, modes: dict) -> dict:
    models: dict[str, dict] = {}
    for r in replies:
        m = models.setdefault(r.model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "_lat": []})
        m["calls"] += 1
        m["prompt_tokens"] += r.prompt_tokens
        m["completion_tokens"] += r.completion_tokens
        m["cost_usd"] += r.cost_usd
        m["_lat"].append(r.latency_s * 1000)
    for m in models.values():
        lat = m.pop("_lat")
        m.update(latency_ms_p50=round(_pct(lat, 0.5), 2), latency_ms_max=round(max(lat), 2), cost_usd=round(m["cost_usd"], 6))
    credits = sum(s.credits for s in searches)
    tavily_cost = round(sum(s.cost_usd for s in searches), 6)
    total = round(sum(m["cost_usd"] for m in models.values()) + tavily_cost, 6)
    mock = any(v == "mock" for v in modes.values())
    return {
        "label": sources.MOCK if mock else "live",
        "modes": modes,
        "models": models,
        "tokens_total": sum(m["prompt_tokens"] + m["completion_tokens"] for m in models.values()),
        "tavily": {"searches": len(searches), "credits": credits, "cost_usd": tavily_cost},
        "cost_usd_total": total,
        "verified_improvements": kept,
        "graduated": graduated,
        "cost_per_verified_improvement_usd": round(total / kept, 6) if kept else None,
        "cheats_caught": refused_ar + refused_self,
        "cheats_caught_autoresearch": refused_ar,
        "cheats_caught_self": refused_self,
        "rules_proposed": rules_proposed,
        "rules_accepted": rules_accepted,
        "prices": {m: {"input_usd_per_m": p[0], "output_usd_per_m": p[1]} for m, p in sources.PRICE_PER_M.items()},
        "prices_source": sources.SOURCES["model_catalog"] + " (read " + sources.FETCHED + ")",
    }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Knos on Nemotron</title>
<style>
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#5d5d58;--line:#e2e1dc;--card:#fff;--accent:#2f6f4f;--warn:#9a5b00}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#151514;--fg:#ecebe6;--muted:#a8a79f;--line:#33332f;--card:#1d1d1b;--accent:#7cc39b;--warn:#e0a54a}}
:root[data-theme="dark"]{--bg:#151514;--fg:#ecebe6;--muted:#a8a79f;--line:#33332f;--card:#1d1d1b;--accent:#7cc39b;--warn:#e0a54a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.muted{color:var(--muted)}.banner{border:1px solid var(--warn);color:var(--warn);border-radius:8px;padding:8px 12px;margin:12px 0;font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
.tile b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.tile span{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:14px;vertical-align:top}th{color:var(--muted);font-weight:600}
.wrap{overflow-x:auto}.ok{color:var(--accent);font-weight:600}.no{color:var(--warn);font-weight:600}code{font-size:13px}
</style></head><body><main>
<h1>Knos builds Knos on Nemotron</h1>
<div class="muted">Nemotron 3 Super proposes, the Knos referee decides, Nemotron 3 Ultra explains refusals (advisory), Tavily checks provenance.</div>
<div id="banner"></div>
<div class="tiles" id="tiles"></div>
<h2>Model calls</h2><div class="wrap"><table id="models"></table></div>
<h2>Experiments (the referee's decisions)</h2><div class="wrap"><table id="exp"></table></div>
<h2>Cheats caught, with the advisory explanation</h2><div class="wrap"><table id="cheats"></table></div>
<h2>Cheat rules proposed from the web</h2><div class="wrap"><table id="rules"></table></div>
<p class="muted" id="foot"></p>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),M=D.metrics,esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const mock=M.label!=='live',tag=mock?' (MOCK)':'';
if(mock)document.getElementById('banner').innerHTML='<div class="banner">'+esc(M.label)+': model replies, token counts, latency and search results are synthetic. The referee\\'s decisions and scores are real runs on synthetic data.</div>';
const usd=x=>x===null?'none':'$'+Number(x).toFixed(6);
const tiles=[[M.tokens_total.toLocaleString(),'tokens'+tag],[usd(M.cost_usd_total),'total cost'+tag],[M.verified_improvements,'verified improvements (kept by the referee)'],
[usd(M.cost_per_verified_improvement_usd),'cost per verified improvement'+tag],[M.cheats_caught,'cheats caught by the referee'],[M.rules_accepted+' of '+M.rules_proposed,'web-found rules accepted by the referee']];
document.getElementById('tiles').innerHTML=tiles.map(t=>'<div class="tile"><b>'+esc(t[0])+'</b><span>'+esc(t[1])+'</span></div>').join('');
document.getElementById('models').innerHTML='<tr><th>model</th><th>calls</th><th>prompt tokens</th><th>completion tokens</th><th>latency p50 ms</th><th>latency max ms</th><th>cost</th></tr>'+
Object.entries(M.models).map(([k,v])=>'<tr><td><code>'+esc(k)+'</code></td><td>'+v.calls+'</td><td>'+v.prompt_tokens+'</td><td>'+v.completion_tokens+'</td><td>'+v.latency_ms_p50+'</td><td>'+v.latency_ms_max+'</td><td>'+usd(v.cost_usd)+'</td></tr>').join('')+
'<tr><td>Tavily search</td><td>'+M.tavily.searches+'</td><td colspan="4">'+M.tavily.credits+' credits</td><td>'+usd(M.tavily.cost_usd)+'</td></tr>';
document.getElementById('exp').innerHTML='<tr><th>#</th><th>proposer</th><th>change</th><th>decision</th></tr>'+(D.experiments||[]).map(e=>'<tr><td>'+e.iteration+'</td><td>'+esc(e.agent)+'</td><td>'+esc(e.change)+'</td><td class="'+(e.decision==='kept'?'ok':e.decision==='refused'?'no':'')+'">'+esc(e.decision)+'</td></tr>').join('');
document.getElementById('cheats').innerHTML='<tr><th>where</th><th>rules (verdict: the referee)</th><th>why, by Nemotron 3 Ultra (advisory)</th></tr>'+(D.cheats||[]).map(c=>'<tr><td>'+esc(c.where)+'</td><td>'+esc(c.verdict)+': '+esc(c.rules.join(', '))+'</td><td>'+esc(c.explanation)+(c.mock?' <i>(MOCK)</i>':'')+'</td></tr>').join('');
document.getElementById('rules').innerHTML='<tr><th>rule</th><th>decision (deterministic)</th><th>reasons</th></tr>'+(D.rules||[]).map(r=>'<tr><td><code>'+esc(r.id)+'</code></td><td class="'+(r.accepted?'ok':'no')+'">'+(r.accepted?'accepted':'rejected')+'</td><td>'+esc((r.reasons||[]).join('; ')||'fires on its known-bad case, silent on its known-good case, adds coverage')+'</td></tr>').join('');
document.getElementById('foot').textContent='Re-runs: '+D.reruns.backend+' ('+D.reruns.reason+'). Prices: '+M.prices_source+'. Generated '+D.generated+'.';
</script></main></body></html>
"""


def write(out_dir: Path, data: dict) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "panel.json"
    js.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    blob = json.dumps(data, default=str).replace("</", "<\\/")
    page = out_dir / "panel.html"
    page.write_text(PAGE.replace("__DATA__", blob), encoding="utf-8")
    return js, page


def text(data: dict) -> str:
    """The same numbers as plain text (what the CLI prints)."""
    m = data["metrics"]
    rows = [f"label: {m['label']}", f"tokens: {m['tokens_total']}", f"cost usd: {m['cost_usd_total']}",
            f"verified improvements: {m['verified_improvements']}",
            f"cost per verified improvement usd: {m['cost_per_verified_improvement_usd'] if m['cost_per_verified_improvement_usd'] is not None else 'none'}",
            f"cheats caught: {m['cheats_caught']}", f"rules accepted: {m['rules_accepted']} of {m['rules_proposed']}",
            f"re-runs: {data['reruns']['backend']}"]
    return "\n".join(rows)
