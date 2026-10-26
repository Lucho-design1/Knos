"""test_entry_text: the private entry text (v0328/research/ENTRY-QLOO-2026-10-30.md, outside every repository) is under
900 words; its first sentence names Qloo and what it decides in Knos; it quotes the where-demand test's numbers as
docs/reference/where_truth.json holds them, the Qloo-set terms' case counts and one real launch city with its target,
and names the buyer; when Knos did not beat Claude alone there, its second sentence leads with the Qloo-set terms; it keeps the writing rules (no em dash, no "not X but Y", no list of three); and
no public repository of drexthealpha lists it (each one's tree on GitHub, read with gh).

    python scripts/test_entry_text.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PRIVATE = Path(os.environ.get("KNOS_PRIVATE_DIR", ".")) / "v0328"
ENTRY = PRIVATE / "research" / "ENTRY-QLOO-2026-10-30.md"
OUT = Path(os.environ.get("KNOS_WORLD", str(PRIVATE / "world"))) / "test_entry_text.txt"
LIST3 = re.compile(r"\b[\w'.-]+(?: [\w'.-]+){0,4}, [\w'.-]+(?: [\w'.-]+){0,4},? (?:and|or) [\w'.-]+")


def main() -> int:
    text = ENTRY.read_text(encoding="utf-8")
    body = re.sub(r"^#.*$", "", text, flags=re.M).strip()
    words = len(text.split())
    sentences = re.split(r"(?<=[.!?])\s", body)
    first, second = sentences[0], sentences[1] if len(sentences) > 1 else ""
    d1 = json.loads((Path(__file__).resolve().parents[1] / "docs" / "reference" / "where_truth.json").read_text(encoding="utf-8"))
    nums = [f"{d1['mean_overlap']['claude_alone']:.3f}", f"{d1['mean_overlap']['knos_with_qloo']:.3f}", f"{d1['difference']:.3f}",
            f"{d1['bootstrap']['interval_95'][0]:.3f}", f"{d1['bootstrap']['interval_95'][1]:.3f}"]
    knos_ahead = d1["bootstrap"]["interval_95"][0] > 0
    checks = [
        (words < 900, f"{words} words (under 900)"),
        ("Qloo" in first and re.search(r"\bdecides?\b", first) is not None, f"first sentence names Qloo and what it decides: {first!r}"),
        (all(n in text for n in nums) and str(d1["n"]) in text, f"the where-demand numbers {nums}, n {d1['n']}"),
        (("Claude alone" in second) if knos_ahead else ("15" in second and "launch city" in second and "5" in second),
         f"the second sentence leads with {'the where-demand result' if knos_ahead else 'the Qloo-set terms (15 with a map, 5 without)'}"),
        ("If fewer than <target> pre-orders come from <city> by the first milestone deadline, every pre-order is refunded." in text
         and "Los Angeles-Long Beach-Anaheim, CA" in text and "125 pre-orders" in text, "the refund rule and a real example: Los Angeles, target 125"),
        ("someone about to build a product" in text, "names the buyer: someone about to build a product"),
        ("\u2014" not in text, "no em dash"),
        (not re.search(r"\bnot\b[^.\n]{0,40}\bbut\b", text, re.I), 'no "not X but Y"'),
        (not LIST3.search(body), f"no list of three{': ' + LIST3.search(body)[0] if LIST3.search(body) else ''}"),
    ]
    repos = json.loads(subprocess.run(["gh", "repo", "list", "drexthealpha", "--visibility", "public", "--limit", "200", "--json", "nameWithOwner,defaultBranchRef"],
                                      capture_output=True, text=True, timeout=120, check=True).stdout)
    listed = []
    for r in repos:
        branch = (r.get("defaultBranchRef") or {}).get("name") or "main"
        tree = subprocess.run(["gh", "api", f"repos/{r['nameWithOwner']}/git/trees/{branch}?recursive=1", "--jq", ".tree[].path"],
                              capture_output=True, text=True, timeout=120)
        if any(p.endswith("ENTRY-QLOO-2026-10-30.md") for p in tree.stdout.splitlines()):
            listed.append(r["nameWithOwner"])
    checks.append((not listed, f"listed by {len(listed)} of {len(repos)} public repositories {listed}"))
    lines = [f"{'ok  ' if c else 'FAIL'} {w}" for c, w in checks]
    bad = sum(not c for c, _ in checks)
    lines.append(f"FAIL test_entry_text: {bad} check(s) failed" if bad else
                 f"PASS test_entry_text: {words} words, Qloo first, D2 terms second, D1 numbers and a real launch city quoted, buyer named, 0 of {len(repos)} public repositories list it")
    print("\n".join(lines))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
