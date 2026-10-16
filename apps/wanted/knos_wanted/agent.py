"""The Knos agent: one crossing from a paper to a funded product, run on the server, calling Qloo at every decision.

    job = start(state, ref="10.1038/nature16521")          # or idea="..." for an idea without a paper
    poll(job_id) -> {"status": "running" | "done" | "error", "steps": [...], "report": hash, "card": hash}

Each step: {n, kind (memory | paper | qloo | decision), title, tool, input, output, effect, at}. Qloo steps stream as the
calls return (check.demand_check(on_call=...)), so the page shows the crossing live by polling GET /api/cross?id=.
Sibyl is the agent's WORKING MEMORY: before a crossing the agent recalls what it learned about the same paper (the
product phrase the maker settled on, the last decision); after it, it remembers this crossing. Memory never moves or
blocks money: escrow rules live in knos_pay on chain.

The same agent answers Model Context Protocol calls at POST /mcp (JSON-RPC over HTTP, tools/list + tools/call), an
optional door for other people's agents; the product is the web page.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import threading
import time

from . import check, company, preorder, research

JOBS: dict[str, dict] = {}
_lock = threading.Lock()
MAX_JOBS = 200


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")


def memory_key(ref: str | None, idea: str | None) -> str:
    return "crossing:" + hashlib.sha256((ref or idea or "").strip().lower().encode()).hexdigest()[:40]


def recall(key: str) -> dict:
    try:
        rec = company._record()
        if rec is None:
            return {}
        got = rec.claim_state(key, root=company.root()) or {}
        return {k: v for k, v in got.items() if not k.startswith("_")}
    except Exception:  # noqa: BLE001 - no memory is a fresh start, never an error
        return {}


def remember(key: str, state: dict) -> dict:
    rec = company._record()
    if rec is None:
        return {"remembered": False, "why": "Sibyl is not installed here"}
    return company._safe(lambda: {"remembered": True, "seq": rec.claim(key, state, domain=company.DOMAIN, root=company.root())["seq"]})


def _step(job: dict, kind: str, title: str, *, tool: str = "", inp=None, out="", effect: str = "") -> dict:
    s = {"n": len(job["steps"]) + 1, "kind": kind, "title": title, "tool": tool, "input": inp, "output": out, "effect": effect, "at": _now()}
    with _lock:
        job["steps"].append(s)
    return s


def _qloo_step(job: dict):
    def on_call(c: dict) -> None:
        effect = next((e for k, e in check.EFFECTS if c["what"].startswith(k)), "evidence")
        _step(job, "qloo", c["what"], tool=c["call"], inp=c.get("params"), out=c.get("error") or c.get("body_digest") or "", effect=effect)
    return on_call


def run(job: dict, state) -> None:
    try:
        key = memory_key(job.get("ref"), job.get("idea"))
        mem = recall(key)
        product = job.get("product")
        if mem:
            if not product and mem.get("product"):
                product = mem["product"]
            _step(job, "memory", "the agent remembers this paper", tool="Sibyl (agent memory)", inp=key,
                  out=f"last crossed {mem.get('when')}: product '{mem.get('product')}', decision {mem.get('verdict')}",
                  effect="reuses the product phrase it settled on last time" if product == mem.get("product") else "noted")
        else:
            _step(job, "memory", "nothing remembered about this paper yet", tool="Sibyl (agent memory)", inp=key, out="first crossing",
                  effect="starts fresh")
        card = None
        if job.get("ref"):
            card = research.research_card(job["ref"], product=product)
            with _lock:
                state.cards[card["hash"]] = card
            job["card"] = card["hash"]
            _step(job, "paper", "read the paper", tool="OpenAlex, Crossref (knos.ideas.sources)", inp=job["ref"],
                  out=f"{card['title'][:120]} ({card.get('year')}), cited {card.get('cited_by_count')}, "
                      f"retracted: {card['retraction']['retracted']}" + (f", Nobel {card['nobel']['prize']} {card['nobel']['year']}" if card.get("nobel") else ""),
                  effect=f"proven result: \"{card['proven_result']['quote'][:160]}\"")
            _step(job, "decision", "the product this result enables", tool="research.product_phrase", inp=card.get("topics"),
                  out=card["product"], effect=card["product_source"])
        idea = (product or (card or {}).get("product") or job.get("idea") or "").strip()
        rep = check.demand_check(idea, job.get("place"), job.get("leader"), client=state.rest, on_call=_qloo_step(job))
        rep["fees"] = preorder.fee_line()
        if card:
            rep["research"] = {**card, "why_never_crossed": research.why_never_crossed(card, rep)}
        rep["record"] = company.record_check(rep)
        state.keep_check(rep)
        job["report"] = rep["hash"]
        d = rep["decision"]
        plan = d.get("plan") or {}
        if plan:
            w = plan["who"]
            _step(job, "decision", "WHO: the target audience", tool="from /v2/insights urn:demographics + urn:audience",
                  out=f"{(w.get('age') or '').replace('_', ' ')}, {w.get('gender')}; segments: {', '.join(w.get('segments') or [])}",
                  effect="the product page and the Blink speak to this audience")
            _step(job, "decision", "WHERE: the launch cities", tool="from /v2/insights urn:entity:destination (explainability on)",
                  out=", ".join(plan.get("where") or []) or "none returned", effect="pre-orders open first in these cities")
            _step(job, "decision", "PRICE: the tier", tool="from Qloo's spending-habit segments (urn:audience)",
                  out=f"{plan['tier']}: {plan['unit_price']} test units per unit", effect="sets the pre-order's unit price")
            _step(job, "decision", "ESCROW: target and reserve", tool="check.RULES units_formula", inp=d.get("formula"),
                  out=f"target {plan['target_units']} units ({plan['escrow_target']} test units), reserve {plan['reserve_units']} "
                      f"({plan['escrow_reserve']} test units)", effect="the maker is paid on proof once the reserve is pre-ordered")
            if plan.get("unserved_audience"):
                _step(job, "decision", "the audience the leader does not serve", tool="from /v2/analysis/compare or the leader's segments",
                      out=", ".join(plan["unserved_audience"]), effect="the product page leads with it")
        _step(job, "decision", f"DECISION: {d['verdict']}", tool="check.decide (code, no language model)", out="; ".join(d["reasons"])[:600],
              effect="pre-orders open" if d["verdict"] == "OPEN" else "no pre-orders")
        if card:
            for w in rep["research"]["why_never_crossed"]:
                _step(job, "decision", f"why it never crossed: {w['wall']}", tool="research.why_never_crossed", out=w["evidence"],
                      effect="flagged" if w["flag"] else "not flagged")
        r = remember(key, {"when": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"), "product": idea, "verdict": d["verdict"],
                           "report": rep["hash"], "target_units": d.get("target_units")})
        _step(job, "memory", "the agent remembers this crossing", tool="Sibyl (agent memory)", inp=key,
              out="remembered" if r.get("remembered") else r.get("why", "not remembered"), effect="the next crossing of this paper starts from here")
        job["status"] = "done"
    except Exception as e:  # noqa: BLE001 - the page shows one plain line; the log has the rest
        job["status"] = "error"
        job["error"] = str(e)[:300] if isinstance(e, ValueError) else "the crossing stopped on a server error"
        print(f"knos agent error {job['id']}: {type(e).__name__}: {str(e)[:300]}", flush=True)
    finally:
        job["finished"] = time.time()


def start(state, *, ref: str | None = None, idea: str | None = None, place: str | None = None, product: str | None = None,
          leader: str | None = None, wait: bool = False) -> dict:
    if not (ref or idea):
        raise ValueError("paste a paper id (DOI, arXiv, PubMed, OpenAlex) or describe an idea")
    job = {"id": secrets.token_hex(8), "ref": ref, "idea": idea, "place": place, "product": product, "leader": leader,
           "status": "running", "steps": [], "started": time.time(), "report": None, "card": None}
    with _lock:
        JOBS[job["id"]] = job
        for k in sorted(JOBS, key=lambda k: JOBS[k]["started"])[:-MAX_JOBS]:
            JOBS.pop(k)
    if wait:
        run(job, state)
    else:
        threading.Thread(target=run, args=(job, state), daemon=True).start()
    return job


def poll(job_id: str, since: int = 0) -> dict | None:
    job = JOBS.get(job_id)
    if job is None:
        return None
    with _lock:
        return {k: v for k, v in job.items() if k != "steps"} | {"steps": job["steps"][since:], "total": len(job["steps"])}


# ---- MCP over HTTP (an optional door for other agents) ----------------------------------------------------------------
PROTOCOL = "2025-06-18"
TOOLS = [
    {"name": "knos_cross", "title": "Cross a paper to a funded product",
     "description": "Paper id (DOI, arXiv, PubMed, OpenAlex) -> research card -> Qloo evidence at every decision -> who, where, price "
                    "tier, escrow target and reserve, and OPEN or REFUSE. Returns every step with its Qloo call, input, output and effect.",
     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "idea": {"type": "string"}, "place": {"type": "string"},
                                                       "product": {"type": "string"}}, "additionalProperties": False}},
    {"name": "knos_research_card", "title": "Read a landmark paper",
     "description": "Paper id -> the proven result (quoted), citations, retraction status, Nobel recognition, the product it enables.",
     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"], "additionalProperties": False}},
    {"name": "knos_demand_check", "title": "Is this product wanted? (Qloo)",
     "description": "A product idea -> Qloo evidence -> a decision made by code.",
     "inputSchema": {"type": "object", "properties": {"idea": {"type": "string"}, "place": {"type": "string"}}, "required": ["idea"],
                     "additionalProperties": False}},
]


def mcp(state, msg: dict) -> dict | None:
    """One JSON-RPC message of the Streamable HTTP transport (POST /mcp). Notifications get no answer (None)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "knos-demand-check", "version": "0.3.34"},
                   "instructions": "Call knos_cross with a paper id; every step names the Qloo call behind it."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        try:
            if name == "knos_cross":
                job = start(state, ref=args.get("ref"), idea=args.get("idea"), place=args.get("place"), product=args.get("product"), wait=True)
                rep = state.report(job["report"]) if job.get("report") else None
                out = {"status": job["status"], "error": job.get("error"), "steps": job["steps"], "report": job.get("report"),
                       "decision": (rep or {}).get("decision")}
            elif name == "knos_research_card":
                out = research.research_card(str(args.get("ref") or ""))
            elif name == "knos_demand_check":
                rep = check.demand_check(str(args.get("idea") or ""), args.get("place"), client=state.rest)
                state.keep_check(rep)
                out = {"report": rep["hash"], "decision": rep["decision"], "calls": rep["calls"]}
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        except ValueError as e:
            return ok({"isError": True, "content": [{"type": "text", "text": str(e)[:300]}]})
        import json
        return ok({"content": [{"type": "text", "text": json.dumps(out, default=str)[:60_000]}], "structuredContent": out})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
