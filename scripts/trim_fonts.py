"""The two fonts the first paint waits for, cut to what the pages use: Geist to weights 400-700, Bricolage Grotesque
(headings and the brand: 600, 650, 700) to 600-700, each to the characters the site's own files hold plus Latin-1.
They were 70.7 KB together, every byte on a slow phone's first paint (the fonts are display: optional and fetched at
once); trimmed, 50 KB. Run it on the Fontsource 5.3.0 originals (web/fonts/LICENSE.txt names their sha256):

    python scripts/trim_fonts.py <folder with the original geist.woff2 and bricolage-grotesque.woff2>

needs fontTools and brotli. It writes web/fonts/; scripts/sync_brand.py copies them into the app. The @font-face
weight ranges in web/brand/tokens.css say the same ranges.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RANGES = {"geist.woff2": (400, 700), "bricolage-grotesque.woff2": (600, 700)}
BASIC = set(range(0x20, 0x7F)) | set(range(0xA0, 0x100)) | set(range(0x2010, 0x2060))


def characters() -> set[int]:
    out = set(BASIC)
    for p in (ROOT / "web").rglob("*"):
        if p.suffix in (".html", ".js", ".css", ".json", ".svg") and p.is_file():
            out |= {ord(c) for c in p.read_text(encoding="utf-8", errors="ignore") if ord(c) >= 0x20}
    return out


def main(argv: list[str]) -> int:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    src, chars = Path(argv[0]), characters()
    for name, (lo, hi) in RANGES.items():
        f = instancer.instantiateVariableFont(TTFont(src / name), {"wght": (lo, hi)})
        opts = subset.Options()
        opts.flavor, opts.layout_features = "woff2", ["*"]
        s = subset.Subsetter(opts)
        s.populate(unicodes=chars)
        s.subset(f)
        f.flavor = "woff2"
        f.save(ROOT / "web" / "fonts" / name)
        print(f"{name}: weights {lo}-{hi}, {(src / name).stat().st_size} -> {(ROOT / 'web' / 'fonts' / name).stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
