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



def _knos_version() -> str:
    """The knos package's version: from the checkout's pyproject.toml when knos is imported from a source tree (where
    installed metadata may be another release's), else knos.version(), the same answer as `knos --version`."""
    try:
        import re
        from pathlib import Path

        import knos
        root = Path(knos.__file__).resolve().parents[2]
        if (root / "src" / "knos").is_dir() and (root / "pyproject.toml").is_file():
            m = re.search(r'(?m)^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"))
            if m:
                return m.group(1)
        return knos.version()
    except Exception:  # noqa: BLE001 - the handshake still answers without knos
        return "unknown"

def _trim(text, n: int) -> str:
    """At most `n` characters, cut at a word boundary with an ellipsis (never mid-word)."""
    t = str(text or "")
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "\u2026"


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


def _store():
    rec = company._record()
    if rec is None:
        return None
    try:
        from knos.record import journal
        return journal.sibyl(company.root())
    except Exception:  # noqa: BLE001
        return None


def hot_get(key: str) -> dict:
    st = _store()
    try:
        return (st.state(key) if st else None) or {}
    except Exception:  # noqa: BLE001
        return {}


def hot_set(key: str, body: dict) -> bool:
    st = _store()
    try:
        if st is None:
            return False
        st.set_state(key, body)
        return True
    except Exception:  # noqa: BLE001
        return False


def shelve_paper(card: dict) -> dict:
    """The paper joins the agent's REFERENCE shelf (title, ids, counts: public literature facts, never idea text)."""
    rec = company._record()
    if rec is None:
        return {"shelved": False, "why": "no record here"}
    return company._safe(lambda: {"shelved": True, "seq": rec.paper("paper:" + (card["ids"].get("doi") or card["ref"]),
                                  {"title": card["title"], "year": card.get("year"), "cited_by_count": card.get("cited_by_count"),
                                   "doi": card["ids"].get("doi"), "card_hash": card["hash"], "product": card["product"]},
                                  domain=company.DOMAIN, root=company.root())["seq"]})


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
    refused = False
    key = memory_key(job.get("ref"), job.get("idea"))
    try:
        held = hot_get("lock:" + key)
        other = held.get("running")
        if other and other != job["id"] and JOBS.get(other, {}).get("status") == "running":
            refused = True
            _step(job, "memory", "another agent holds this crossing", tool="Sibyl HOT state (the shared working plan)",
                  inp="lock:" + key, out=f"crossing {other} is running the same paper now: this agent's conflicting "
                  "writes are REFUSED; it reads along and writes nothing",
                  effect="one plan per crossing; memory stays consistent")
        else:
            hot_set("lock:" + key, {"running": job["id"], "started": job["started"],
                                    "plan": ["recall memory", "read the paper", "name the product", "ask Qloo (who, where, "
                                             "price, trend, leader)", "decide by code", "remember the crossing"]})
            _step(job, "memory", "the agent's plan, in shared memory", tool="Sibyl HOT state (crossing plan + cursor)",
                  inp="lock:" + key, out="plan written: recall -> paper -> product -> Qloo evidence -> decision -> remember",
                  effect="a second agent on the same paper is refused while this one runs")
        try:
            if getattr(state.q, "mode", "") == "live":
                words = " ".join((job.get("product") or job.get("idea") or job.get("ref") or "").split()[:6]) or "research product"
                cap = state.q.call("qloo_find_tags", {"query": words},
                                   why="the official qloo-harness MCP server reads Qloo beside the REST steps", step="harness")
                names = ", ".join(str(r.get("name")) for r in (cap.get("results") or [])[:4])
                _step(job, "qloo", "the Qloo harness answers (live)", tool="qloo mcp (official @qloo/qloo-harness, via the Node bridge)",
                      inp={"tool": "qloo_find_tags", "query": words}, out=f"status {cap.get('status')}: {names}"[:200],
                      effect="the ten harness tools answer at /mcp as qloo_*; the decision reads below run on the REST API, labelled")
        except Exception:  # noqa: BLE001 - a harness that is down never stops a crossing; REST carries it, labelled
            _step(job, "qloo", "the Qloo harness is down: REST carries this crossing", tool="qloo mcp (not reachable)",
                  out="falling back to the REST API, labelled on every step", effect="same evidence, same rules")
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
                  out=f"{_trim(card['title'], 120)} ({card.get('year')}), cited {card.get('cited_by_count')}, "
                      f"retracted: {card['retraction']['retracted']}"
                      + (f", Nobel {card['nobel']['prize']} {card['nobel']['year']}" if card.get("nobel") else "")
                      + (f"; regulated: the source cites {card['regulator']}" if card.get("regulator") else ""),
                  effect=f"proven result: \"{_trim(card['proven_result']['quote'], 160)}\"")
            _step(job, "decision", "the product this result enables", tool="research.product_phrase", inp=card.get("topics"),
                  out=card["product"], effect=card["product_source"])
            if not refused:
                shelf = shelve_paper(card)
                _step(job, "memory", "the paper on the reference shelf", tool="Sibyl REFERENCE tier (knos.record paper line)",
                      inp=card["ids"].get("doi") or job.get("ref"),
                      out=f"seq {shelf.get('seq')}" if shelf.get("shelved") else shelf.get("why", "not shelved"),
                      effect="later crossings and searches find this paper without re-reading it")
            if not refused:
                hot_set("lock:" + key, {**hot_get("lock:" + key), "cursor": "qloo evidence"})
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
        if refused:
            _step(job, "memory", "nothing written: the other agent holds this crossing", tool="Sibyl (agent memory)", inp=key,
                  out="conflicting write refused", effect="the running agent's record stays the one record")
        else:
            r = remember(key, {"when": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"), "product": idea, "verdict": d["verdict"],
                               "report": rep["hash"], "target_units": d.get("target_units")})
            hot_set("lock:" + key, {"running": None, "last_report": rep["hash"]})
            _step(job, "memory", "the agent remembers this crossing", tool="Sibyl (agent memory: WARM state + COLD journal)", inp=key,
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


def crossings(state, n: int = 30) -> list[dict]:
    """Every crossing this server ran, newest first: what the Buyer view lists so a result is never lost."""
    out = []
    with _lock:
        jobs = sorted(JOBS.values(), key=lambda j: j["started"], reverse=True)[:n]
    for j in jobs:
        rep = state.report(j["report"]) if j.get("report") else None
        d = (rep or {}).get("decision") or {}
        out.append({"id": j["id"], "status": j["status"], "ref": j.get("ref"), "idea": (rep or {}).get("idea") or j.get("idea"),
                    "report": j.get("report"), "verdict": d.get("verdict"), "target_units": d.get("target_units"),
                    "reserve_units": d.get("reserve_units"), "started": j["started"]})
    return out


def poll(job_id: str, since: int = 0) -> dict | None:
    job = JOBS.get(job_id)
    if job is None:
        return None
    with _lock:
        return {k: v for k, v in job.items() if k != "steps"} | {"steps": job["steps"][since:], "total": len(job["steps"])}


# ---- MCP over HTTP (an optional door for other agents) ----------------------------------------------------------------
PROTOCOL = "2025-06-18"
CONFIRM = ("CONFIRM FIRST: this moves devnet TEST money or posts work. Ask the human you work for before calling, and "
           "pass the session token knos_sign_in returned. Test money only; no real funds.")
DISCOVERY = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Knos MCP</title><link rel="stylesheet" href="/static/style.css"></head><body><main class="wrap">
<h1>Knos over MCP</h1>
<p>This endpoint speaks the Model Context Protocol (Streamable HTTP, JSON-RPC): <code class="url">POST /mcp</code>.
Add it by URL in Claude, Cursor or any MCP client. Reading needs no key; money tools take a session token from
<span class="mono">knos_sign_in</span> and say in their descriptions to confirm with your human first. Everything is
Solana devnet test money.</p>
<p>Tools: knos_cross, knos_research_card, knos_demand_check, knos_crossings, knos_milestones, knos_tasks,
knos_memory_recall, knos_sign_in, knos_preorder, knos_evidence, knos_task_submit.</p>
<p><a href="/">The app</a> · <a href="/verify">How we verify</a></p></main></body></html>"""
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
    {"name": "knos_crossings", "title": "Crossings on this server",
     "description": "Every crossing this server ran, newest first: id, paper or idea, verdict, report hash.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "knos_milestones", "title": "Open milestones",
     "description": "Every commitment on this server: escrow order, units, status, claim id. A locked one needs an evidence page.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "knos_tasks", "title": "Open work for contributors",
     "description": "Open game rounds and milestones a person or agent can work on; judged and paid on devnet (test money).",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "knos_memory_search", "title": "Search everything this Knos remembers",
     "description": "FTS5 search (multilingual) over the agents' memory and the Knos Record: papers, crossings, decisions, events.",
     "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"], "additionalProperties": False}},
    {"name": "knos_memory_recall", "title": "What the agent remembers about a paper",
     "description": "Sibyl, the crossing agent's working memory: the last crossing of a paper or idea (product phrase, verdict, report).",
     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "idea": {"type": "string"}}, "additionalProperties": False}},
    {"name": "knos_sign_in", "title": "A session for the money tools",
     "description": "Returns a session token the money tools need. " + CONFIRM,
     "inputSchema": {"type": "object", "properties": {"label": {"type": "string", "description": "who your human is (a display label)"}},
                     "required": ["label"], "additionalProperties": False}},
    {"name": "knos_preorder", "title": "Pre-order with the demo buyer",
     "description": "Locks units of an OPEN report in devnet escrow through the app's demo buyer. " + CONFIRM,
     "inputSchema": {"type": "object", "properties": {"report": {"type": "string"}, "units": {"type": "integer"},
                                                       "session": {"type": "string"}}, "required": ["report", "units", "session"],
                     "additionalProperties": False}},
    {"name": "knos_evidence", "title": "Post milestone evidence",
     "description": "Posts a milestone's public evidence page; verified evidence releases the escrow to the maker. " + CONFIRM,
     "inputSchema": {"type": "object", "properties": {"commitment": {"type": "string"}, "evidence_url": {"type": "string"},
                                                       "session": {"type": "string"}}, "required": ["commitment", "evidence_url", "session"],
                     "additionalProperties": False}},
    {"name": "knos_task_submit", "title": "Submit work to an open round",
     "description": "Submits the whole train.py to the open round (knos_tasks says what to change and links the task's README); "
                    "the sealed referee judges it at once; several attempts per round. A scored attempt with a devnet `wallet` "
                    "is paid a demo prize in test units. " + CONFIRM,
     "inputSchema": {"type": "object", "properties": {"round": {"type": "string"}, "name": {"type": "string"}, "code": {"type": "string"},
                                                       "wallet": {"type": "string"},
                                                       "session": {"type": "string"}}, "required": ["round", "code", "session"],
                     "additionalProperties": False}},
]


def _signed(args: dict) -> dict:
    from . import auth
    who = auth.who("Bearer " + str(args.get("session") or ""))
    if who is None:
        raise ValueError("session: sign in first with knos_sign_in (and confirm with your human)")
    return who


def mcp(state, msg: dict) -> dict | None:
    """One JSON-RPC message of the Streamable HTTP transport (POST /mcp). Notifications get no answer (None)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "knos-demand-check", "version": _knos_version()},
                   "instructions": "Call knos_cross with a paper id; every step names the Qloo call behind it."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        extra = []
        try:
            from .qloo_mcp import WORKFLOWS
            mode = getattr(state.q, "mode", "mock")
            extra = [{"name": n, "title": n.replace("_", " "),
                      "description": f"The official qloo-harness tool {n}, proxied from this server's `qloo mcp` "
                                     f"({'LIVE' if mode == 'live' else 'MOCK synthetic data, labelled in every answer'}).",
                      "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True}}
                     for n in ("qloo_capabilities",) + WORKFLOWS]
        except Exception:  # noqa: BLE001
            extra = []
        return ok({"tools": TOOLS + extra})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if isinstance(name, str) and name.startswith("qloo_"):
            from .qloo_mcp import WORKFLOWS, QlooUnavailable
            if name not in ("qloo_capabilities",) + WORKFLOWS:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
            import json as _json
            try:
                got = state.q.call(name, dict(args), why="proxied for an outside agent over Knos's MCP", step=name)
            except QlooUnavailable as e:
                return ok({"isError": True, "content": [{"type": "text", "text": str(e)[:300]}]})
            return ok({"content": [{"type": "text", "text": _json.dumps(got, default=str)[:60_000]}], "structuredContent": got})
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
            elif name == "knos_crossings":
                out = {"crossings": crossings(state)}
            elif name == "knos_milestones":
                out = {"commitments": preorder.all_public(50)}
            elif name == "knos_tasks":
                from . import tasks as _tasks
                out = _tasks.listing()
            elif name == "knos_memory_search":
                from knos.record import search as rsearch
                got = rsearch.search(str(args.get("q") or "")[:200], root=company.root())
                out = {"said": got.get("said"), "rows": got.get("rows", [])[:20]}
            elif name == "knos_memory_recall":
                out = recall(memory_key(args.get("ref"), args.get("idea"))) or {"remembered": False}
            elif name == "knos_sign_in":
                from . import auth
                out = auth.guest(str(args.get("label") or "agent") + " (via MCP)")
            elif name == "knos_preorder":
                who = _signed(args)
                rep = state.report(str(args.get("report") or ""))
                if rep is None:
                    raise ValueError("unknown report: run knos_cross first")
                out = preorder.lock(rep, int(args.get("units") or 0), f"{who.get('kind')}: {who.get('label')}")
            elif name == "knos_evidence":
                who = _signed(args)
                rec = preorder.load(str(args.get("commitment") or ""))
                out = preorder.milestone(state.report(rec["report"]) or {}, rec["order"], str(args.get("evidence_url") or ""))
            elif name == "knos_task_submit":
                who = _signed(args)
                from . import tasks as _tasks
                out = _tasks.submit(str(args.get("round") or ""), str(args.get("name") or ""), str(args.get("code") or ""),
                                    f"{who.get('kind')}: {who.get('label')}", sub=str(who.get("sub") or ""),
                                    wallet=str(args.get("wallet") or "") or None)
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        except ValueError as e:
            return ok({"isError": True, "content": [{"type": "text", "text": str(e)[:300]}]})
        import json
        return ok({"content": [{"type": "text", "text": json.dumps(out, default=str)[:60_000]}], "structuredContent": out})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
