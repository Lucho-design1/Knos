"""What each Qloo signal changes: for each recorded sample chip and each Qloo call family its card used, the verdict,
the launch city and the pre-order target recomputed with that family's answer removed, by check.py's own rules
(decide, and metros.terms for the city and the target). Offline, from the private recordings; what it writes holds
derived values only (labels, Census metro names, numbers), never a Qloo answer.

    python scripts/qloo_ablation.py <private recordings file>          write docs/reference/qloo_ablation.json and the page's table
    python scripts/qloo_ablation.py <private recordings file> --check  exit 1 when either differs
"""
from __future__ import annotations

import copy
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "wanted"), str(ROOT / "src")]
from knos_wanted import check, metros  # noqa: E402

OUT = ROOT / "docs" / "reference" / "qloo_ablation.json"
PAGE = ROOT / "web" / "how-we-test.html"
START, END = "<!-- ablation:start -->", "<!-- ablation:end -->"
# a Qloo call family -> the report fields its answers fill (check.gather), and what they are when it is removed
FAMILIES = {
    "search (the matched products)": {"matches": [], "leader": None, "tags": []},
    "demographics": {"who": None},
    "audiences": {"audiences": [], "who_wants": [], "buyer_group": None},
    "compare (the leader)": {"versus": None},
    "trending": {"trend": {}},
    "recommendations": {"recommended": None},
    "heatmap": {"where": []},
    "destinations": {"cities": []},
    "places": {"places": []},
    "tags (persona)": {"persona": [], "persona_all": []},
    "brand ladder": {"ladder": []},
}


def outcome(rep: dict) -> dict:
    d = check.decide(rep, True, rep.get("idea") or "")
    t = metros.terms(rep.get("where") or [])
    return {"label": d["verdict"], "city": t["city"] if t else None, "target": t["target"] if t else None}


def used(rep: dict, fields: dict) -> bool:
    return any(rep.get(k) not in (None, [], {}) for k in fields)


def rows(cards: dict) -> list[dict]:
    out = []
    for key in sorted(cards):
        rep = cards[key]
        before = outcome(rep)
        for fam, fields in FAMILIES.items():
            if not used(rep, fields):
                continue
            after = outcome({**copy.deepcopy(rep), **copy.deepcopy(fields)})
            out.append({"chip": rep.get("idea"), "removed": fam, "city": [before["city"], after["city"]],
                        "target": [before["target"], after["target"]], "label": [before["label"], after["label"]]})
        nothing = check.decide(rep, False, rep.get("idea") or "")
        out.append({"chip": rep.get("idea"), "removed": "every Qloo answer", "city": [before["city"], None], "target": [before["target"], None],
                    "label": [before["label"], nothing["verdict"]]})
    return out


def table(rs: list[dict]) -> str:
    e = lambda v: html.escape("none" if v is None else str(v))  # noqa: E731
    body = "".join(f"<tr><td>{e(r['chip'])}</td><td>{e(r['removed'])}</td><td>{e(r['city'][0])} → {e(r['city'][1])}</td>"
                   f"<td>{e(r['target'][0])} → {e(r['target'][1])}</td><td>{e(r['label'][0])} → {e(r['label'][1])}</td></tr>" for r in rs)
    changed = sum(r["city"][0] != r["city"][1] or r["target"][0] != r["target"][1] or r["label"][0] != r["label"][1] for r in rs)
    return (f'{START}\n    <section class="t" id="ablation">\n      <h2>What each Qloo signal changes</h2>\n'
            f'      <p class="t-n">{len(rs)} removals on 6 recorded samples: {changed} change the city, the target or the verdict.</p>\n'
            f'      <details><summary>The table</summary><div class="k-table"><table>\n'
            f'        <thead><tr><th scope="col">Sample</th><th scope="col">Removed</th><th scope="col">Launch city</th><th scope="col">Target</th><th scope="col">Verdict</th></tr></thead>\n'
            f'        <tbody>{body}</tbody>\n      </table></div></details>\n'
            f'      <p class="fine">Recomputed by the check\'s own rules from cards recorded on 22 Oct 2026; live, the later questions are asked from the search\'s matches (<a href="https://github.com/drexthealpha/Knos/blob/main/docs/reference/qloo_ablation.json" rel="noopener">the values</a>).</p>\n'
            f'    </section>\n    {END}')


def main(argv: list[str]) -> int:
    cards = json.loads(Path(argv[0]).read_text(encoding="utf-8"))["cards"]
    rs = rows(cards)
    doc = {"about": "derived values only: the verdict, the launch city (a Census metro) and the target, before and after each removal",
           "rules": "apps/wanted/knos_wanted/check.py decide, metros.terms", "samples": len(cards), "rows": rs}
    page = PAGE.read_text(encoding="utf-8")
    if START in page:
        a, b = page.index(START), page.index(END) + len(END)
        new_page = page[:a] + table(rs) + page[b:]
    else:
        anchor = '    <section class="t" id="board">'
        new_page = page.replace(anchor, "    " + table(rs) + "\n" + anchor, 1)
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if "--check" in argv:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text and new_page == page
        print("ablation table is current" if same else "ablation table differs: run python scripts/qloo_ablation.py <file>")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    PAGE.write_text(new_page, encoding="utf-8", newline="\n")
    print(f"{len(rs)} rows written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
