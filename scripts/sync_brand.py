"""Knos's one design system, written onto every public page: the front door's (web/) and the app's
(apps/wanted/knos_wanted/static/).

    python scripts/sync_brand.py            write
    python scripts/sync_brand.py --check    exit 1 if a page or a copy differs from what this writes

The token file (web/brand/tokens.css), the wordmark, the mark, the fonts and the bar's script (web/brand/bar.js) are
copied byte for byte to the app's static/brand/ and static/fonts/. The bar (web/brand/bar.html) is written between
`<!-- k-bar -->` and `<!-- /k-bar -->` on each page with the same words, links and order everywhere; only the start of
each address changes, so that a link to the page's own site stays on it ({H} its home, {S} the front door, {A} the
app). Each page loads the token file before its own stylesheet.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB, STATIC = ROOT / "web", ROOT / "apps" / "wanted" / "knos_wanted" / "static"
SITE = "https://drexthealpha.github.io/Knos/"
# the front door names no other host in its pages (tests/test_settle_fixtures.py): its links to the app go through its own
# wake page, which wakes the free server and forwards (web/wanted.html: the hash, and ?to= one of the app's pages)
WAKE = "wanted.html"
COPIES = {WEB / "brand" / n: STATIC / "brand" / n for n in ("tokens.css", "wordmark.svg", "mark.svg", "bar.js", "hero.js")}
COPIES |= {f: STATIC / "fonts" / f.name for f in sorted((WEB / "fonts").iterdir()) if f.suffix in (".woff2", ".txt")}
# page: (its home, the front door, the app, its tokens link, loads web/brand/bar.js)
PAGES = {
    WEB / "index.html": ("", "", WAKE, "brand/tokens.css", False),        # web/front.js runs this bar
    WEB / "faq.html": ("./", "./", WAKE, "brand/tokens.css", True),
    WEB / "privacy.html": ("./", "./", WAKE, "brand/tokens.css", True),
    WEB / "404.html": (SITE, SITE, SITE + WAKE, "brand/tokens.css", True),        # its <base href="/Knos/"> holds at any depth
    WEB / "wanted.html": ("./", "./", WAKE, "brand/tokens.css", True),
    STATIC / "index.html": ("", SITE, "", "/static/brand/tokens.css", True),
    **{STATIC / n: ("/", SITE, "/", "/static/brand/tokens.css", True)
       for n in ("trace.html", "with_without.html", "qloo_safe_use.html", "invite.html", "verify.html")},
}
MARK = re.compile(r"<!-- k-bar -->.*?<!-- /k-bar -->", re.S)
HERO = re.compile(r"<!-- k-hero -->.*?<!-- /k-hero -->", re.S)
# the two front doors' first screens: (the app's address for the API, the app's address for its pages, hero.js)
HEROES = {WEB / "index.html": ("@app", WAKE, "brand/hero.js"), STATIC / "index.html": ("", "/", "/static/brand/hero.js")}


def bar(home: str, site: str, app: str) -> str:
    t = (WEB / "brand" / "bar.html").read_text(encoding="utf-8").strip()
    # a page of the app is at the app's root, a page of the site at the site's: {AP}/{SP} start a page's address
    pages = app + "?to=/" if app.endswith(WAKE) else (app or "/")
    return t.replace("{H}", home).replace("{SP}", site or "./").replace("{S}", site).replace("{AP}", pages).replace("{A}", app)


def page(path: Path, home: str, site: str, app: str, tokens: str, script: bool) -> str:
    s = path.read_text(encoding="utf-8")
    src = "/static/brand/bar.js" if tokens.startswith("/static/") else tokens.replace("tokens.css", "bar.js")
    block = f"<!-- k-bar -->\n{bar(home, site, app)}\n" + (f'<script src="{src}" defer></script>\n' if script else "") + "<!-- /k-bar -->"
    if MARK.search(s):
        s = MARK.sub(lambda _: block, s, count=1)
    else:
        # the page's own header gives way to the bar; a page with none gets it first in the body
        s, n = re.subn(r"<header\b.*?</header>", lambda _: block, s, count=1, flags=re.S)
        if not n:
            s = re.sub(r"<body([^>]*)>", lambda m: f"<body{m.group(1)}>\n{block}", s, count=1)
    if path in HEROES:
        api, app_pages, js = HEROES[path]
        t = (WEB / "brand" / "hero.html").read_text(encoding="utf-8").strip().replace("{API}", api).replace("{APP}", app_pages)
        s = HERO.sub(lambda _: f'<!-- k-hero -->\n{t}\n<script src="{js}" defer></script>\n<!-- /k-hero -->', s, count=1)
    # the two fonts of the first paint are asked for with the page, as the front door does (no swap after it)
    fonts = tokens.replace("brand/tokens.css", "fonts/")
    for f in ("geist.woff2", "bricolage-grotesque.woff2"):
        pre = f'<link rel="preload" href="{fonts}{f}" as="font" type="font/woff2" crossorigin>'
        if f'fonts/{f}" as="font"' not in s:
            s = s.replace("</head>", f"{pre}\n</head>", 1) if '<link rel="stylesheet"' not in s else \
                re.sub(r'(<link rel="stylesheet")', lambda m, pre=pre: f"{pre}\n{m.group(1)}", s, count=1)
    link = f'<link rel="stylesheet" href="{tokens}">'
    if link not in s:
        s = re.sub(r'(<link rel="stylesheet")', lambda m: f"{link}\n{m.group(1)}", s, count=1) if "<link rel=\"stylesheet\"" in s \
            else s.replace("</head>", f"{link}\n</head>", 1)
    return s


def main(argv: list[str]) -> int:
    check, off = "--check" in argv, []
    for a, b in COPIES.items():
        if not b.exists() or b.read_bytes() != a.read_bytes():
            off.append(str(b.relative_to(ROOT)))
            if not check:
                b.parent.mkdir(parents=True, exist_ok=True)
                b.write_bytes(a.read_bytes())
    for path, args in PAGES.items():
        new = page(path, *args)
        if new != path.read_text(encoding="utf-8"):
            off.append(str(path.relative_to(ROOT)))
            if not check:
                path.write_text(new, encoding="utf-8", newline="\n")
    print(("differs: " if check else "wrote: ") + (", ".join(off) or "nothing"))
    return 1 if check and off else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
