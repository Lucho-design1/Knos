"""Write the IDT benchmark's measured numbers into the home page (web/index.html, between <!-- home:idt --> marks).

    python scripts/idt_page.py          write the block from docs/idt/summary.json
    python scripts/idt_page.py --check  exit 1 when the page and the data disagree (tests/test_idt.py runs it)

The block is a sentence and a table, all from the measured runs (scripts/idt_bench.py): output tokens as Claude Code's
print mode returned them, pass or fail of each task's own check. Nothing is estimated."""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "index.html"
DATA = ROOT / "docs" / "idt" / "summary.json"
RAW = "https://github.com/drexthealpha/Knos/blob/main/docs/idt/runs.json"
PACKAGED = ROOT / "src" / "knos" / "idt_benchmark.json"
MARK = re.compile(r"(<!-- home:idt -->)(.*?)(<!-- /home:idt -->)", re.S)


def block(s: dict) -> str:
    n = f"{s['tasks']}"
    pct = lambda x: f"{round(100 * x)}%"  # noqa: E731
    rows = "".join(
        f"<tr><td>{html.escape(r['task'])}</td><td class=\"k-num\">{r['vague_output_tokens']:,}</td><td class=\"k-num\">{r['ready_output_tokens']:,}</td>"
        f"<td class=\"k-num\">{r['saved_output_tokens']:+,}</td><td>{'yes' if r['vague_passed'] else 'no'} / {'yes' if r['ready_passed'] else 'no'}</td></tr>"
        for r in s["rows"])
    return (f"\n    <section id=\"home-idt\" aria-label=\"IDT benchmark\" data-ratio=\"{s['ratio_vague_to_ready']}\">"
            f"<p class=\"fine\" id=\"idt-line\">Clear briefs: <strong class=\"k-num\" id=\"idt-ratio\">{s['ratio_vague_to_ready']}x</strong> fewer reasoning tokens, measured on {n} tasks.</p>"
            f"<details class=\"k-more\" id=\"idt-per-brief\" data-not-prose><summary>Each brief</summary>"
            f"<p class=\"fine\">One model ({html.escape(str(s['model']))}, {html.escape(str(s['effort']))} effort) for both. Vague: {s['vague_output_tokens']:,} tokens, {pct(s['vague_pass_rate'])} passed. "
            f"Ready: {s['ready_output_tokens']:,} tokens, {pct(s['ready_pass_rate'])} passed.</p>"
            f"<div class=\"k-table\"><table><thead><tr><th scope=\"col\">Task</th><th scope=\"col\">Vague</th><th scope=\"col\">Ready</th>"
            f"<th scope=\"col\">Saved</th><th scope=\"col\">Passed</th></tr></thead><tbody>{rows}</tbody></table></div>"
            f"<p class=\"fine\">Output tokens include thinking. <a href=\"{RAW}\" rel=\"noopener\">Every run, raw</a>.</p></details></section>\n    ")


def packaged(s: dict) -> str:
    """The benchmark as the server reads it (knos.idt.benchmark_for): each task's two briefs and measured tokens."""
    tasks = {t["id"]: t for t in json.loads((ROOT / "bench" / "idt" / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
    keep = ("task", "kind", "vague_output_tokens", "ready_output_tokens", "saved_output_tokens", "vague_passed", "ready_passed")
    rows = [{**{k: r[k] for k in keep}, "vague": tasks[r["task"]]["vague"], "ready": tasks[r["task"]]["ready"]} for r in s["rows"]]
    return json.dumps({"v": 1, "model": s["model"], "effort": s["effort"], "tasks": s["tasks"], "ratio_vague_to_ready": s["ratio_vague_to_ready"],
                       "raw": RAW, "rows": rows}, indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    s = json.loads(DATA.read_text(encoding="utf-8"))
    page = PAGE.read_text(encoding="utf-8")
    m = MARK.search(page)
    if not m:
        print("web/index.html has no <!-- home:idt --> block", file=sys.stderr)
        return 1
    want = block(s)
    if check:
        ok = m.group(2) == want and PACKAGED.exists() and PACKAGED.read_text(encoding="utf-8") == packaged(s)
        print("the home page's IDT numbers match docs/idt/summary.json" if ok else "the home page's IDT numbers differ from docs/idt/summary.json")
        return 0 if ok else 1
    PAGE.write_text(page[:m.start(2)] + want + page[m.end(2):], encoding="utf-8", newline="\n")
    PACKAGED.write_text(packaged(s), encoding="utf-8", newline="\n")
    print(f"wrote the IDT block: ratio {s['ratio_vague_to_ready']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
