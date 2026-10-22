"""The built front door carries its two stylesheets in the page (TASK-CHAMPION T7): each was a render-blocking request
before the first paint. Their font and image addresses are rewritten for the page's place at the site's root.

    python scripts/inline_css.py _site/index.html
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    page = Path(argv[0])
    site = page.parent
    html = page.read_text(encoding="utf-8")
    tokens = (site / "brand" / "tokens.css").read_text(encoding="utf-8")
    tokens = tokens.replace('url("../fonts/', 'url("fonts/').replace('url("mark.svg")', 'url("brand/mark.svg")') \
        .replace('url("wordmark.svg")', 'url("brand/wordmark.svg")')
    done = 0
    for link, css in (('<link rel="stylesheet" href="brand/tokens.css">', tokens),
                      ('<link rel="stylesheet" href="app.css">', (site / "app.css").read_text(encoding="utf-8"))):
        if link in html:
            html, done = html.replace(link, f"<style>{css}</style>", 1), done + 1
    page.write_text(html, encoding="utf-8", newline="\n")
    print(f"inline css: {done} stylesheets written into {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
