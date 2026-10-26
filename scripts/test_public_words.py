"""test_public_words: what a reader of Knos's public files and pages reads. "escrow" in no README, document,
description or rendered page text (code identifiers listed apart); no "48-hour"; no private path; no hackathon host
in the deploy values; the pricing page's exact sentence and no Kickstarter or Upwork market figure; the two links that
were broken answer 200.

    python scripts/test_public_words.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = Path(os.environ.get("KNOS_WORLD") or Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328" / "world")
OUT = WORLD / "test_public_words.txt"
PRICING = "Free check. At mainnet the funder pays 1% on top of each payout; the solver keeps 100%."
LINKS = ["https://github.com/drexthealpha/Knos/blob/main/evidence/knos-witness-acaa854d/witness.json",     # README "the record"
         "https://github.com/drexthealpha/Knos/blob/main/docs/idt/summary.json"]                          # PyPI README's IDT link
# the receipt's trust line: its words are pinned by conformance kit version 1 (docs/receipt/vectors*.json, whose digests
# cover them); a changed line is a new receipt format, so they stay, and are counted here apart
RECEIPT_FORMAT = {"src/knos/receipt.py", "docs/reference/RECEIPT.md", "web/buyer_templates.json", "docs/receipt/vectors.json",
                  "docs/receipt/vectors.v4.json", "docs/receipt/vectors.v5.json", "examples/consumer/fixtures/order_paid.json",
                  "examples/consumer/fixtures/receipt.json", "integrations/webhook/fixtures.json"}


def files(*globs: str) -> list[str]:
    return subprocess.run(["git", "ls-files", *globs], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()


def prose(rel: str, text: str) -> str:
    """What a reader reads: Markdown without its code; a page without its scripts, styles and tags."""
    if rel.endswith(".md"):
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        return re.sub(r"`[^`\n]*`", " ", text)
    if rel.endswith(".html"):
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
        return re.sub(r"<[^>]+>", " ", text)
    return text


def descriptions() -> dict[str, str]:
    out = {}
    for rel in files("*Cargo.toml"):
        m = re.search(r'(?m)^description = "(.*)"$', (ROOT / rel).read_text(encoding="utf-8"))
        if m:
            out[rel] = m.group(1)
    for rel in files("*package.json", "server.json", "gemini-extension.json"):
        try:
            d = json.loads((ROOT / rel).read_text(encoding="utf-8")).get("description")
        except (ValueError, AttributeError):
            d = None
        if isinstance(d, str):
            out[rel] = d
    m = re.search(r'(?m)^description = "(.*)"$', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    out["pyproject.toml"] = m.group(1)
    return out


def status(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": "knos-test"}), timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> int:
    lines, fails = [], 0

    def ok(c: bool, what: str) -> None:
        nonlocal fails
        lines.append(f"{'ok  ' if c else 'FAIL'} {what}")
        fails += not c
    public = [r for r in files("README.md", "README.pypi.md", "docs/*.md", "docs/reference/*.md", "web/*.html", "web/check/*.html",
                               "apps/wanted/knos_wanted/static/*.html", "sdk/*/README.md", "idl/README.md", "integrations/*/README.md")]
    texts = {r: prose(r, (ROOT / r).read_text(encoding="utf-8")) for r in public}
    texts.update({f"{r} (description)": d for r, d in descriptions().items()})
    esc = {r: len(re.findall(r"escrow", t, re.I)) for r, t in texts.items()}
    esc = {r: n for r, n in esc.items() if n}
    ok(not esc, f'"escrow" in public prose, descriptions and rendered page text: {sum(esc.values())} {esc}')
    code = subprocess.run(["git", "grep", "-o", "-h", "-i", r"[A-Za-z_.]*escrow[A-Za-z_.]*", "--", *public], cwd=ROOT, capture_output=True, text=True).stdout.split()
    lines.append(f"     code identifiers kept (in code spans and code, never read as prose): {sorted(set(code))}")
    hour = {r: n for r in files() if not r.startswith(("tests/", "CHANGELOG")) and (ROOT / r).is_file()
            for n in [(ROOT / r).read_bytes().count(b"48-hour")] if n}
    rest = {r: n for r, n in hour.items() if r not in RECEIPT_FORMAT}
    ok(not hour, f'"48-hour": {sum(hour.values())} {hour} (receipt format, pinned by conformance kit version 1: '
                 f'{ {r: n for r, n in hour.items() if r in RECEIPT_FORMAT} }; elsewhere: {sum(rest.values())})')
    private = subprocess.run(["git", "grep", "-l", "-i", "knos-v1-private"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    ok(not private, f"private paths: {len(private)} {private}")
    host = subprocess.run(["git", "grep", "-l", "hackathon" + ".api.qloo.com"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    ok(not host, f"the hackathon host in any file (deploy values included): {len(host)} {host}")
    pricing = " ".join(prose("p.html", (ROOT / "web" / "pricing.html").read_text(encoding="utf-8")).split())
    ok(PRICING in pricing, f'pricing.html says exactly "{PRICING}"')
    market = " ".join(prose("p.html", (ROOT / "web" / "how-we-test.html").read_text(encoding="utf-8")).split())
    ok(not re.search(r"kickstarter|upwork", pricing, re.I), f"Kickstarter or Upwork in pricing.html: {len(re.findall(r'kickstarter|upwork', pricing, re.I))}")
    ok(not re.search(r"market|billion|trillion", market, re.I), "how-we-test.html states no market figure (its Kickstarter tests are published results and stay)")
    for u in LINKS:
        ok(status(u) == 200, f"{status(u)} {u}")
    lines.append(f"FAIL test_public_words: {fails} check(s) failed" if fails else
                 "PASS test_public_words: 0 escrow in public prose, 0 48-hour, 0 private paths, 0 hackathon host, pricing exact, both links 200")
    print("\n".join(lines))
    WORLD.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
