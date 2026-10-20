"""The IDT benchmark: what a vague brief costs a model next to a Ready brief, measured, never estimated.

    python scripts/idt_bench.py [--model sonnet] [--effort medium] [--only c01,r03] [--out docs/idt]

Every task of bench/idt/tasks.json is run twice through Claude Code in print mode on the operator's own subscription
(`claude -p --output-format json`, never --bare, which skips that login): once with the vague brief, once with the
Ready brief, same model, same effort, no tools. From each run's JSON: output tokens (thinking is billed as output),
thinking tokens, input and cache tokens, and the client's cost estimate (total_cost_usd). Each run is cross-checked
against its own session transcript (~/.claude/projects/<cwd>/<session_id>.jsonl, the per-message usage). The answer
is the reply's last fenced code block; the check is the task's: asserts run on the Python, or knos.ready.check on the
JSON brief. Writes <out>/runs.json (every run, raw) and <out>/summary.json (per task and in total)."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FENCE = re.compile(r"```(?:python|json|py)?\s*\n(.*?)```", re.S)


def answer(text: str) -> str:
    blocks = FENCE.findall(text or "")
    return blocks[-1].strip() if blocks else ""


def check(task: dict, reply: str) -> tuple[bool, str]:
    code = answer(reply)
    if not code:
        return False, "no fenced code block"
    if task["kind"] == "code":
        want = re.match(r"\s*(\w+)\(", task["asserts"][0]).group(1)
        # a vague brief names no function: the reply's first function is tested under the name the check uses
        alias = (f"\nif {want!r} not in globals():\n    import inspect as _i\n"
                 f"    _f = [v for k, v in list(globals().items()) if _i.isfunction(v) and not k.startswith('_')]\n"
                 f"    if _f:\n        {want} = _f[0]\n")
        prog = code + alias + "\n".join(f"assert {a}, {a!r}" for a in task["asserts"]) + "\nprint('ok')\n"
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(prog)
        try:
            r = subprocess.run([sys.executable, "-I", f.name], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return False, "timed out"
        finally:
            os.unlink(f.name)
        return (r.returncode == 0 and r.stdout.strip().endswith("ok")), (r.stderr.strip().splitlines() or ["ok"])[-1][:200]
    from knos import ready
    try:
        brief = json.loads(code)
    except ValueError as why:
        return False, f"not JSON: {why}"[:200]
    got = ready.check(brief)
    return got["ready"], "Ready" if got["ready"] else "; ".join(got["missing"][:4])[:200]


def overthinking(task: dict, r: dict) -> dict | None:
    """The overthinking ratio (M): the share of the reply after the first code block that already passes the check.
    Detectable only for code tasks whose reply has a passing block; None otherwise."""
    from knos import idt
    if task["kind"] != "code":
        return None
    fence = "`" * 3
    return idt.overthinking(r.get("reply") or "", r.get("output_tokens") or 0,
                            lambda code: check(task, f"{fence}python\n{code}\n{fence}")[0])


def transcript_usage(session: str) -> dict | None:
    """The session's own record of what was billed: the sum of its assistant messages' usage."""
    base = Path.home() / ".claude" / "projects"
    for f in base.glob(f"*/{session}.jsonl"):
        out, seen = {"output_tokens": 0, "input_tokens": 0, "messages": 0}, set()
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            m = e.get("message") or {}
            u = m.get("usage") if e.get("type") == "assistant" else None
            if not u or m.get("id") in seen:          # one API message may be written as several entries
                continue
            seen.add(m.get("id"))
            out["output_tokens"] += u.get("output_tokens", 0)
            out["input_tokens"] += u.get("input_tokens", 0)
            out["messages"] += 1
        return {**out, "file": f.name}
    return None


def run(brief: str, model: str, effort: str, cwd: Path) -> dict:
    t = time.time()
    p = subprocess.run(["claude.cmd" if os.name == "nt" else "claude", "-p", "--output-format", "json", "--model", model, "--effort", effort, "--tools", ""],
                       input=brief, capture_output=True, text=True, encoding="utf-8", timeout=900, cwd=cwd)
    try:
        j = json.loads(p.stdout)
    except ValueError:
        return {"error": (p.stderr or p.stdout)[-300:], "seconds": round(time.time() - t, 1)}
    u = j.get("usage") or {}
    return {"session_id": j.get("session_id"), "is_error": j.get("is_error"), "seconds": round(time.time() - t, 1),
            "output_tokens": u.get("output_tokens", 0), "thinking_tokens": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
            "input_tokens": u.get("input_tokens", 0), "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0), "cost_usd": j.get("total_cost_usd"),
            "num_turns": j.get("num_turns"), "model_usage": list((j.get("modelUsage") or {}).keys()), "reply": j.get("result") or ""}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=str(ROOT / "docs" / "idt"))
    ap.add_argument("--recheck", action="store_true", help="score the stored replies again; no model call")
    a = ap.parse_args(argv)
    tasks = json.loads((ROOT / "bench" / "idt" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    if a.only:
        tasks = [t for t in tasks if t["id"] in a.only.split(",")]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    runs_f = out / "runs.json"
    runs = json.loads(runs_f.read_text(encoding="utf-8")) if runs_f.exists() else []
    if a.recheck:
        by_id = {t["id"]: t for t in json.loads((ROOT / "bench" / "idt" / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
        for r in runs:
            if not r.get("error") and not r.get("is_error"):
                r["passed"], r["check"] = check(by_id[r["task"]], r["reply"])
                r["overthinking"] = overthinking(by_id[r["task"]], r)
        runs_f.write_text(json.dumps(runs, indent=1, ensure_ascii=False), encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(summary(runs), indent=1), encoding="utf-8")
        return 0
    cwd = Path(tempfile.gettempdir()) / "knos-idt-bench"
    cwd.mkdir(exist_ok=True)
    for t in tasks:
        for which in ("vague", "ready"):
            if any(r["task"] == t["id"] and r["brief"] == which and not r.get("error") and not r.get("is_error") for r in runs):
                continue
            r = run(t[which], a.model, a.effort, cwd)
            if not r.get("error") and not r.get("is_error"):
                r["passed"], r["check"] = check(t, r["reply"])
                r["transcript"] = transcript_usage(r["session_id"]) if r.get("session_id") else None
                r["overthinking"] = overthinking(t, r)
            runs = [x for x in runs if not (x["task"] == t["id"] and x["brief"] == which)]
            runs.append({"task": t["id"], "kind": t["kind"], "brief": which, "model": a.model, "effort": a.effort,
                         "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **r})
            runs_f.write_text(json.dumps(runs, indent=1, ensure_ascii=False), encoding="utf-8")
            print(t["id"], which, r.get("output_tokens"), r.get("passed"), r.get("check") or r.get("error") or "", flush=True)
    (out / "summary.json").write_text(json.dumps(summary(runs), indent=1), encoding="utf-8")
    return 0


def summary(runs: list[dict]) -> dict:
    ok = [r for r in runs if not r.get("error") and not r.get("is_error")]
    by = {}
    for r in ok:
        by.setdefault(r["task"], {})[r["brief"]] = r
    rows = []
    for tid, b in sorted(by.items()):
        if "vague" in b and "ready" in b:
            v, rd = b["vague"], b["ready"]
            rows.append({"task": tid, "kind": v["kind"], "vague_output_tokens": v["output_tokens"], "ready_output_tokens": rd["output_tokens"],
                         "saved_output_tokens": v["output_tokens"] - rd["output_tokens"],
                         "vague_passed": v["passed"], "ready_passed": rd["passed"],
                         "vague_cost_usd": v.get("cost_usd"), "ready_cost_usd": rd.get("cost_usd"),
                         "transcript_matches": all((x.get("transcript") or {}).get("output_tokens") == x["output_tokens"] for x in (v, rd))})
    tv = sum(r["vague_output_tokens"] for r in rows)
    tr = sum(r["ready_output_tokens"] for r in rows)
    n = len(rows)
    return {"v": 1, "tasks": n, "model": ok[0]["model"] if ok else None, "effort": ok[0]["effort"] if ok else None,
            "measured_with": "claude -p --output-format json (Claude Code print mode, the operator's subscription); usage as the API returned it",
            "vague_output_tokens": tv, "ready_output_tokens": tr, "ratio_vague_to_ready": round(tv / tr, 2) if tr else None,
            "saved_share": round(1 - tr / tv, 3) if tv else None,
            "vague_pass_rate": round(sum(r["vague_passed"] for r in rows) / n, 3) if n else None,
            "ready_pass_rate": round(sum(r["ready_passed"] for r in rows) / n, 3) if n else None,
            "vague_cost_usd": round(sum(r["vague_cost_usd"] or 0 for r in rows), 4), "ready_cost_usd": round(sum(r["ready_cost_usd"] or 0 for r in rows), 4),
            "transcripts_match": all(r["transcript_matches"] for r in rows), "rows": rows}


if __name__ == "__main__":
    sys.exit(main())
