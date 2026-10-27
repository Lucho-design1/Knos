"""A result's three downloads, from its /r/<id> page: the brief as a one-page PDF (the print layout's fields: the idea,
the verdict, the launch city and target, the launch cities, the calls and the page's address), the Qloo calls as CSV
(endpoint, parameters without any key, ms, cached, the part of the card each fed; never a response body) and the Ready
brief as JSON (with its criteria hash; none when Qloo set no launch city). Nothing here asks Qloo."""
from __future__ import annotations

import csv
import io
import json
import re

from . import metros, result_page

SECRET = re.compile(r"key|token|secret|auth|password", re.I)


def csv_text(rep: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["n", "endpoint", "params", "ms", "cached", "fed"])
    for c in rep.get("calls") or []:
        if not isinstance(c, dict):
            continue
        params = "; ".join(f"{k}={v}" for k, v in (c.get("params") or {}).items() if v not in (None, "") and not SECRET.search(str(k)))
        w.writerow([c.get("n"), c.get("call"), params, c.get("ms") if isinstance(c.get("ms"), (int, float)) else "", "yes" if c.get("cached") else "no",
                    c.get("what") or c.get("effect") or ""])
    return out.getvalue()


def brief_doc(rep: dict) -> dict:
    t = rep.get("terms") if isinstance(rep.get("terms"), dict) and metros.launch_terms(rep) else None
    if not t:
        return {"ready": False, "brief": None, "idea": rep.get("idea"), "report": rep.get("hash"),
                "why": "Qloo set no launch city for this idea, so there is no Ready brief to lock money on."}
    from knos import ready
    persona = [x.get("name") for x in rep.get("persona") or [] if isinstance(x, dict) and x.get("name")]
    b = metros.brief(str(rep.get("idea") or ""), t, persona)
    return {"ready": True, "brief": b, "criteria_hash": ready.criteria_hash(b), "idea": rep.get("idea"), "report": rep.get("hash")}


def _ascii(s: str) -> str:
    return str(s).encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf(rep: dict, url: str) -> bytes:
    """One A4 page of text in Helvetica: the fields the /r/ page prints."""
    t = result_page.terms_of(rep)
    word = result_page.WORD.get(str((rep.get("decision") or {}).get("verdict") or ""), "Qloo cannot decide this one")
    if word == result_page.WORD["OPEN"] and not t:
        word = "Not yet: Qloo sets no launch city for this idea"
    rows = [(16, f"Knos. {rep.get('idea') or 'this idea'}"), (12, word)]
    if t:
        rows += [(11, f"Launch city: {t['city']}"), (11, f"Pre-order target: {t['target']}, all refunded if it falls short"),
                 (11, f"Launch cities: {', '.join(t['cities'])}")]
    rows += [(11, f"Qloo calls: {len(rep.get('calls') or [])}, read {str(rep.get('made') or '')[:10]}"),
             (9, "Aggregate taste of many people from Qloo, never about one person."), (9, url), (9, "Devnet, test money.")]
    y, ops = 800, []
    for size, text in rows:
        for part in [text[i:i + 90] for i in range(0, len(text), 90)] or [""]:
            ops.append(f"BT /F1 {size} Tf 50 {y} Td ({_ascii(part)}) Tj ET")
            y -= size + 8
    stream = "\n".join(ops).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def json_text(rep: dict) -> str:
    return json.dumps(brief_doc(rep), indent=1, ensure_ascii=False)
