"""test_recorded_persist: the sample chips' recorded cards survive a redeploy. A fresh local server (KNOS_TEST_MODE=1,
QLOO_FORCE_STATUS=429) reads them from the private recordings file and each chip with a recording answers with it,
marked stale with its real UTC time; then one live check of the deployed app (Qloo refusing it) does the same. Neither
the repository nor a Pages build holds any of the recorded Qloo answers.

    python scripts/test_recorded_persist.py <private recordings file> <site dir of a fresh build> <commit sha under test>
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
OUT = WORLD / "test_recorded_persist.txt"
APP = "https://knos.onrender.com"
sys.path[:0] = [str(ROOT / "apps" / "wanted"), str(ROOT / "src")]
from knos_wanted import recorded  # noqa: E402


def post(base: str, idea: str, timeout: float = 240) -> dict:
    req = urllib.request.Request(base + "/api/check", data=json.dumps({"idea": idea}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "knos-test-recorded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_http": e.code}


def secret_strings(cards: dict) -> list[str]:
    """Distinctive strings of the recorded answers (body digests and long names Qloo returned), to look for in public files."""
    out = set()
    for rep in cards.values():
        out |= {c["body_digest"] for c in rep.get("calls") or [] if c.get("body_digest")}
        for p in rep.get("persona") or []:
            if len(str(p.get("name") or "")) >= 12:
                out.add(str(p["name"]))
    # a line Knos's own code writes into a card (check.py: "answer received" when a call answered) is not Qloo's
    own = " ".join(f.read_text(encoding="utf-8") for f in (ROOT / "apps" / "wanted" / "knos_wanted").glob("*.py"))
    return sorted(m for m in out if m not in own)


def main(file: str, site: str, sha: str) -> int:
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    cards = json.loads(Path(file).read_text(encoding="utf-8"))["cards"]
    times = {k: v["made"] for k, v in cards.items()}
    lines.append(f"recordings: {len(cards)} of {len(recorded.CHIPS)} chips; " + "; ".join(f"{k}: {t}" for k, t in sorted(times.items())))
    missing = [c for c in recorded.CHIPS if recorded.key(c) not in cards]
    lines.append(f"no recording (no real card saved before 25 Oct 16:00 UTC, and Qloo has refused since): {missing}")
    # 1. a fresh local server with Qloo refusing
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "KNOS_TEST_MODE": "1", "QLOO_FORCE_STATUS": "429", "KNOS_RECORDED_FILE": file, "PORT": str(port),
           "HOST": "127.0.0.1", "KNOS_WANTED_SEED": "0", "PYTHONPATH": os.pathsep.join([str(ROOT / "apps" / "wanted"), str(ROOT / "src")]),
           "QLOO_API_KEY": "test-key-not-real", "QLOO_BASE_URL": "https://example.test"}
    proc = subprocess.Popen([sys.executable, "-m", "knos_wanted", "serve"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=2)
                break
            except OSError:
                time.sleep(1)
        for chip in recorded.CHIPS[:7]:                     # the paper goes through a crossing and has no recording
            got = post(base, chip)
            k = recorded.key(chip)
            st = got.get("stale") or {}
            if k in cards:
                ok(st.get("code") == 429 and st.get("from") == cards[k]["made"] and got.get("hash") == cards[k]["hash"],
                   f"local, fresh server, Qloo 429: {chip}: recorded card from {st.get('from')} (HTTP {st.get('code')})")
            else:
                ok((got.get("qloo_down") or {}).get("code") == 429 and not st, f"local: {chip}: no recording, the card says Qloo is not answering")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    # 2. the deployed app, after its redeploy at the commit under test
    dep = subprocess.run([sys.executable, "-I", os.environ["KNOS_RENDER_LATEST"]], capture_output=True, text=True).stdout.splitlines() if os.environ.get("KNOS_RENDER_LATEST") else []
    ok(bool(dep) and dep[0].endswith(sha[:8]) and " live " in dep[0], f"Render's newest deploy: {dep[0] if dep else 'not read'} (commit under test {sha[:8]})")
    live = {}
    for chip in recorded.CHIPS[:7]:
        k = recorded.key(chip)
        if k not in cards:
            continue
        got = post(APP, chip)
        st = got.get("stale") or {}
        live[k] = st.get("from")
        ok(st.get("from") == cards[k]["made"], f"live {APP}: {chip}: recorded card from {st.get('from')} (HTTP {st.get('code')})")
    # 3. none of it public
    marks = secret_strings(cards)
    in_git = [m for m in marks if subprocess.run(["git", "grep", "-q", "-F", m], cwd=ROOT).returncode == 0]
    in_site = [m for m in marks for f in Path(site).rglob("*") if f.is_file() and f.stat().st_size < 20_000_000
               and m.encode() in f.read_bytes()][:5]
    ok(not in_git and not in_site, f"Qloo response bodies of the recordings ({len(marks)} distinctive strings): {len(in_git)} in git, {len(in_site)} in the Pages build")
    lines.append(f"FAIL test_recorded_persist: {fails} check(s) failed" if fails else
                 f"PASS test_recorded_persist: {len(cards)} of 8 chips recorded ({min(times.values())} to {max(times.values())}); each shown after a fresh redeploy with Qloo refusing, locally and live; 0 bodies public")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
