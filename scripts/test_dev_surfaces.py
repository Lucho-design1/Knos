"""test_dev_surfaces (N7), live: each developer surface, checked in a fresh venv built from the wheel (not -e).

    python scripts/test_dev_surfaces.py <commit sha under test> <out file> <scratch dir>

(a) `knos idea wanted` answers from the hosted check, labelled "hosted"; (b) `knos status` says an approved upgrade as a
warning and exits 0 when nothing else fails; (c) every documented OpenAPI example of a read-only route answers neither
400 nor 404 (scripts/openapi_examples.mjs), and HTML, SSE, JS and 301 routes say so; (d) `knos idt check` prints what is
missing and exits 1 when not ready; (e) `knos demand` prints three lines with the reason, its help puts the flags after
the usage, and `knos --help` lists demand, idt and idea first; (f) README.md's paid transaction is described as
`knos receipt verify` describes it; (g) the knos-settle README quotes a funded issue, live, and warns on statement()'s
time; (h) the MCP server is named "knos".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://knos.onrender.com"
lines: list[str] = []
fails = 0


def ok(c: bool, what: str) -> None:
    global fails
    lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
    fails += not c


def run(args: list[str], env: dict | None = None, cwd: Path | None = None, timeout: int = 600) -> tuple[int, str]:
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=cwd, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main(sha: str, out: str, scratch: str) -> int:
    s = Path(scratch)
    dep = json.loads(run(["gh", "api", "repos/drexthealpha/Knos/deployments?environment=github-pages&per_page=1"])[1])[0]
    ok(dep["sha"] == sha, f"Pages deployed at {dep['sha'][:7]} (commit under test {sha[:7]})")
    if os.environ.get("KNOS_RENDER_LATEST"):          # a script printing Render's newest deploy: "<id> <status> <sha>"
        latest = run([sys.executable, "-I", os.environ["KNOS_RENDER_LATEST"]])[1].split()
        ok(len(latest) > 2 and latest[1] == "live" and sha.startswith(latest[2]), f"Render live at {latest[2] if len(latest) > 2 else '?'}")
    # the wheel, and a venv with nothing else
    whl, venv = s / "n7wheel", s / "n7venv"
    for d in (whl, venv):
        shutil.rmtree(d, ignore_errors=True)
    code, said = run([sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-w", str(whl)], timeout=900)
    wheel = next(whl.glob("knos-*.whl"), None)
    ok(code == 0 and wheel is not None, f"wheel built: {wheel.name if wheel else said[-200:]}")
    run([sys.executable, "-m", "venv", str(venv)])
    bin_ = venv / ("Scripts" if os.name == "nt" else "bin")
    exe = ".exe" if os.name == "nt" else ""
    py, knos = bin_ / f"python{exe}", bin_ / f"knos{exe}"
    code, said = run([str(py), "-m", "pip", "install", "-q", str(wheel)], timeout=1800)
    ok(code == 0 and knos.exists(), f"installed from the wheel in a fresh venv (not -e): {'yes' if code == 0 else said[-200:]}")
    certifi = run([str(py), "-c", "import certifi; print(certifi.where())"])[1].strip()
    env = {**os.environ, "SSL_CERT_FILE": certifi, "PYTHONIOENCODING": "utf-8"}
    work = s / "n7work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    kn = lambda *a, **k: run([str(knos), *a], env=env, cwd=work, **k)  # noqa: E731 - from an empty folder: no repository near it
    has = run([str(py), "-c", "import importlib.util as u; print(bool(u.find_spec('knos_wanted')))"], env=env, cwd=work)[1].strip()
    ok(has == "False", f"knos_wanted is not in this install: {has}")
    # (a)
    code, said = kn("idea", "wanted", "doi:10.1038/nature14539")
    ok(code == 0 and re.search(r"demand check: ok hosted", said) is not None and "hosted:" in said, f"(a) knos idea wanted: {' / '.join(x.strip() for x in said.splitlines() if 'demand check' in x or 'hosted' in x)[:200]}")
    # (b)
    code, said = kn("status", timeout=300)
    warn = [x for x in said.splitlines() if x.startswith("WARN")]
    tail = said.strip().splitlines()[-1] if said.strip() else ""
    ok(code == 0 and not any(x.startswith("FAIL") for x in said.splitlines()) and (not warn or all("approved" in x for x in warn)),
       f"(b) knos status exit {code}: {tail}; warnings: {len(warn)}" + (f" ({warn[0][:160]})" if warn else ""))
    # (c)
    code, said = run(["node", str(ROOT / "scripts" / "openapi_examples.mjs"), API], timeout=900)
    (s / "n7_openapi.txt").write_text(said, encoding="utf-8")
    ok(code == 0, f"(c) {said.strip().splitlines()[-1] if said.strip() else 'no output'}")
    doc = json.load(urllib.request.urlopen(API + "/openapi.json", timeout=60))
    def kind(path: str) -> str:
        r = doc["paths"][path]["get"]["responses"]
        return "301" if "301" in r else next(iter((r.get("200") or {}).get("content") or {"none": 0}))
    kinds = {p: kind(p) for p in ("/app/", "/sw.js", "/api/cross/stream", "/", "/api/proofs/cosign.pub")}
    research = (doc["paths"]["/api/research"]["post"].get("requestBody") or {}).get("content", {}).get("application/json", {})
    ok(kinds == {"/app/": "text/html", "/sw.js": "application/javascript", "/api/cross/stream": "text/event-stream", "/": "301", "/api/proofs/cosign.pub": "text/plain"}
       and research.get("example") == {"ref": "10.1038/nature14539"}, f"(c) content types {kinds}; /api/research body example {research.get('example')}")
    # (d)
    (work / "empty.json").write_text("{}", encoding="utf-8")
    code, said = kn("idt", "check", "empty.json")
    got = json.loads(said[said.index("{"):]) if "{" in said else {}
    ok(code == 1 and got.get("missing") and "milestones" in got and got.get("ready") is False, f"(d) knos idt check {{}}: exit {code}, missing {got.get('missing')}")
    # (e)
    code, said = kn("demand", "a cold brew coffee shop", "--place", "Austin")
    rows = [x for x in said.strip().splitlines() if x.strip()]
    ok(code == 0 and "{" not in said and len(rows) == 3 and rows[0].startswith("Verdict:") and rows[1].startswith("Why: ") and len(rows[1]) > 10,
       f"(e) knos demand: {' | '.join(rows)[:260]}")
    code, said = kn("demand", "--help")
    u, o, f = said.find("Usage"), said.find("Options"), said.find("Qloo's options")
    ok(code == 0 and 0 <= u < o < f, f"(e) knos demand --help: Usage at {u}, its Options at {o}, the Qloo flags after them at {f}")
    code, said = kn("--help")
    panel = said[said.find("Commands"):]                 # the commands, from the Commands panel on (Options holds --version, --help)
    cmds = [m.group(1) for m in re.finditer(r"^\W+([a-z][a-z-]+)\s{2,}", panel, re.M)]
    ok(cmds[:3] == ["demand", "idt", "idea"], f"(e) knos --help: the first commands {cmds[:5]}")
    # (f)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    tx = re.search(r"\[paid\]\(https://explorer\.solana\.com/tx/([1-9A-HJ-NP-Za-km-z]{60,90})\?cluster=devnet\) \(([^)]*)\)", readme)
    code, said = kn("receipt", "verify", tx.group(1)) if tx else (1, "")
    phrase = tx.group(2) if tx else ""
    ok(bool(tx) and phrase and phrase in said, f"(f) README's paid transaction \"({phrase})\"; knos receipt verify says: {said.strip()[:200]}")
    # (g)
    sr = (ROOT / "sdk" / "settle" / "README.md").read_text(encoding="utf-8")
    code, said = run(["node", "-e", "import('./sdk/settle/agent.js').then(async (m) => { const o = await m.quote('https://api.devnet.solana.com', 1406351591, 15); "
                      "console.log(JSON.stringify({said: o.said, items: o.items.length})); })"], cwd=ROOT, timeout=300)
    last = (said.strip().splitlines() or [""])[-1]
    q = json.loads(last) if last.startswith("{") else {}
    ok("quote(RPC, 1406351591, 15)" in sr and q.get("items", 0) >= 1 and "467 s" in sr, f"(g) the README quotes 1406351591 #15: {q.get('items')} offer(s), \"{str(q.get('said'))[:120]}\"; statement() warned")
    # (h)
    req = urllib.request.Request(API + "/mcp", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "test_dev_surfaces", "version": "1"}}}).encode(), {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    body = urllib.request.urlopen(req, timeout=60).read().decode()
    name = json.loads(body[body.index("{"):])["result"]["serverInfo"]["name"]
    ok(name == "knos", f"(h) MCP serverInfo name: {name}")
    lines.append(f"FAIL test_dev_surfaces: {fails} check(s) failed" if fails else
                 "PASS test_dev_surfaces: (a) to (h) each checked in a fresh venv from the wheel; the OpenAPI examples: 0 failures")
    print("\n".join(lines))
    with open(out, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
