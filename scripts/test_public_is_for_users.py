"""test_public_is_for_users: what is public is for people who use Knos. No tracked file is a contest submission or a
contest's paperwork (by path), and no public page, in the repository or live, speaks of a hackathon, Devpost or a
submission form (addresses in links are left out: a source Knos cites may have such a name).

    python scripts/test_public_is_for_users.py [--live]
"""
from __future__ import annotations

import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH_WORDS = re.compile(r"submission|devpost|hackathon", re.I)
TEXT_WORDS = re.compile(r"hackathon|devpost|judging period|SUBMISSION\.md", re.I)
GONE = ["SUBMISSION.md", "docs/submission", ".github/workflows/fresh-setup.yml"]
LIVE = ["https://drexthealpha.github.io/Knos/", "https://drexthealpha.github.io/Knos/faq.html", "https://knos.onrender.com/app/",
        "https://knos.onrender.com/with-without", "https://knos.onrender.com/qloo-safe-use", "https://knos.onrender.com/invite",
        "https://knos.onrender.com/trace.html", "https://knos.onrender.com/verify.html"]


def words(html: str) -> str:
    """The text a reader sees and hears: markup and link addresses out, attribute text (alt, aria-label, title) in."""
    html = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", html)
    attrs = " ".join(re.findall(r'(?:alt|aria-label|title|content)="([^"]*)"', html))
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"https?://\S+", " ", text + " " + attrs)


def main() -> int:
    fails = []
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    bad = [p for p in tracked if PATH_WORDS.search(p)]
    print(("ok   " if not bad else "FAIL ") + f"no tracked file is a submission or contest file ({len(tracked)} files)", bad[:5])
    fails += bad
    left = [g for g in GONE if (ROOT / g).exists()]
    print(("ok   " if not left else "FAIL ") + "the submission folder, its text and its setup check are not in the repository", left)
    fails += left
    pages = sorted([*ROOT.glob("web/*.html"), *ROOT.glob("apps/wanted/knos_wanted/static/*.html")])
    said = [(p.relative_to(ROOT).as_posix(), m.group(0)) for p in pages for m in [TEXT_WORDS.search(words(p.read_text(encoding="utf-8")))] if m]
    print(("ok   " if not said else "FAIL ") + f"{len(pages)} public pages in the repository speak of no contest", said)
    fails += said
    if "--live" in sys.argv:
        for url in LIVE:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "knos test_public_is_for_users"}), timeout=90) as r:
                m = TEXT_WORDS.search(words(r.read().decode("utf-8", "replace")))
            print(("ok   " if not m else "FAIL ") + f"live {url}", m.group(0) if m else "")
            fails += [url] if m else []
    print("PASS test_public_is_for_users" if not fails else f"FAIL test_public_is_for_users ({len(fails)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
