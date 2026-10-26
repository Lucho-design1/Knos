"""test_chain_truth: the app's live program FaMHCjzy...JY4 answers to the Squads vault CKCrT... (its 8-day time lock),
README's table of programs is what devnet says today, and every payout linked on the README, the front door and the
app's home says what released it, read from that payout's own transaction (the referee's verdict, or GitHub's
signed check verified on Solana). Reads only; signs nothing.

    python scripts/test_chain_truth.py
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "apps" / "wanted")]
from knos import chain  # noqa: E402

import program_authorities as pa  # noqa: E402

WORLD = Path(os.environ.get("KNOS_WORLD", r"C:\Users\zulab\knos-v1-private\v0328\world"))
OUT = WORLD / "test_chain_truth.txt"
APP_PROGRAM = "FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4"
REFEREE = "Released by the referee's verdict"
GITHUB = "Released by GitHub's signed check, verified on Solana"
TX = re.compile(r"https://explorer\.solana\.com/tx/([1-9A-HJ-NP-Za-km-z]{64,90})\?cluster=devnet")


def released_by(tx: dict | None) -> str | None:
    from knos_wanted.server import released_by as rb       # the app's own reading, the one its pages show
    return rb(tx)


def payout(tx: dict | None) -> bool:
    """A transaction that paid someone: knos_pay's `knos3:paid` log (the app's program) or a pay on merge."""
    logs = ((tx or {}).get("meta") or {}).get("logMessages") or []
    return any("knos3:paid" in line or "knos2:paid" in line or "Instruction: PayOnMerge" in line for line in logs)


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "knos-test-chain-truth"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def blocks(text: str, is_html: bool) -> list[str]:
    """The pieces a reader sees together: an HTML paragraph or list item, or a Markdown line."""
    if is_html:
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S)
        return re.findall(r"<(?:p|li)\b[^>]*>.*?</(?:p|li)>", text, flags=re.S)
    return text.splitlines()


def main() -> int:
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    shown = pa.authority(APP_PROGRAM)
    ok(shown.get("authority") == pa.VAULT, f"{APP_PROGRAM}: upgrade authority on devnet {shown.get('authority')} (want the Squads vault {pa.VAULT})")
    cli = subprocess.run(["wsl", "-d", "Ubuntu-24.04", "-e", "bash", "-lc",
                          f"$HOME/.local/share/solana/install/active_release/bin/solana program show {APP_PROGRAM} -u devnet"],
                         capture_output=True, text=True, timeout=120)
    said = re.search(r"Authority: (\w+)", cli.stdout)
    ok(bool(said) and said.group(1) == pa.VAULT, f"solana program show {APP_PROGRAM[:8]}...: Authority {said.group(1) if said else cli.stderr[:120]}")
    chk = subprocess.run([sys.executable, str(ROOT / "scripts" / "program_authorities.py"), "--check"], capture_output=True, text=True, timeout=300)
    ok(chk.returncode == 0, f"README's program table against devnet today: {chk.stdout.strip().splitlines()[-1] if chk.stdout.strip() else chk.stderr[-200:]}")
    doc = json.loads((ROOT / "docs" / "program_authorities.json").read_text(encoding="utf-8"))
    ok(any(r["address"] == APP_PROGRAM and "the app's live program (0.3.34)" in r["name"] for r in doc["programs"]),
       "the table names FaMHCjzy...JY4 as the app's live program (0.3.34)")
    surfaces = [("README.md (main)", (ROOT / "README.md").read_text(encoding="utf-8"), False),
                ("front door https://drexthealpha.github.io/Knos/", get("https://drexthealpha.github.io/Knos/"), True),
                ("app home https://knos.onrender.com/", get("https://knos.onrender.com/"), True)]
    seen = 0
    for name, text, is_html in surfaces:
        for b in blocks(text, is_html):
            for sig in TX.findall(b):
                tx = chain.call(chain.DEVNET_URL, "getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
                if not payout(tx):
                    continue
                seen += 1
                want = released_by(tx)
                words = html.unescape(re.sub(r"<[^>]+>", " ", b)) if is_html else b
                wrong = (GITHUB if want == REFEREE else REFEREE)
                ok(bool(want) and want in words and wrong not in words, f"{name}: payout {sig[:10]}... says {want!r}")
    latest = json.loads(get("https://knos.onrender.com/api/agent/payout/latest"))
    if latest.get("found"):
        seen += 1
        tx = chain.call(chain.DEVNET_URL, "getTransaction", [latest["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        ok(latest.get("released") == released_by(tx) and latest.get("released"),
           f"app /api/agent/payout/latest {latest['signature'][:10]}...: released {latest.get('released')!r}, its transaction says {released_by(tx)!r} (the front door shows this field)")
    ok(seen > 0, f"{seen} payout links checked on the three surfaces")
    lines.append(f"FAIL test_chain_truth: {fails} check(s) failed" if fails else
                 f"PASS test_chain_truth: FaMHCjzy answers to {pa.VAULT[:5]}..., {len(doc['programs'])} programs match devnet, {seen} payout links labelled by what released them")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
