"""knos.yml: what a research repository claims, and how Knos re-runs it.

    knos: 1
    name: tiny-centroid
    entry: python train.py --split {split} --seed {seed} --data {data} --out {out}
    data:
      generator: python make_data.py --seed {data_seed} --out {data}
      seed: 7
      protected: [data/, results.json]
    splits:
      public: test
      heldout: heldout
    claims:
      - id: accuracy
        metric: accuracy
        expected: 0.9
        tolerance: 0.03
        reported: {file: results.json, key: accuracy}
    compute:
      max_seconds: 300
    seed: 0
    authors:
      - github: someone
    funding: https://example.org/pre-order

The file is read by a small, strict parser of the YAML subset above (block maps, block lists, lists of maps, scalars,
inline `[a, b]` lists and inline `{k: v}` maps of scalars), so a knos.yml means the same thing on every machine
whatever YAML library is installed. Anything the parser does not know is an error, never a guess.

Placeholders in `entry` and `data.generator`: {split}, {seed}, {data}, {out}, {data_seed}. The entry writes a JSON object
of metrics to {out}; each claim names one key of it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

FORMAT = 1
FILE = "knos.yml"
PLACEHOLDERS = ("split", "seed", "data", "out", "data_seed")
MAX_SECONDS = 6 * 3600          # a compute budget above this is refused: a reproduction is a check, not a training run


class SpecError(ValueError):
    """knos.yml is not a spec Knos can run. The text says which field and why."""


# ---- the YAML subset ---------------------------------------------------------------------------------------------------

_KEY = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s+(.*))?$")
_INT = re.compile(r"^[-+]?\d+$")
_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


def _strip_comment(line: str) -> str:
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _split_top(text: str, sep: str = ",") -> list[str]:
    parts, depth, quote, cur = [], 0, "", ""
    for ch in text:
        if quote:
            cur += ch
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts]


def scalar(text: str):
    """One YAML scalar of the subset: quoted text, [a, b], {k: v}, true/false, null, a number, else plain text."""
    t = text.strip()
    if not t:
        return None
    if t[0] in "'\"":
        if len(t) < 2 or t[-1] != t[0]:
            raise SpecError(f"unterminated quoted text: {t[:60]}")
        inner = t[1:-1]
        return inner.replace("''", "'") if t[0] == "'" else json.loads('"' + inner.replace('\\"', '\\u0022') + '"')
    if t[0] == "[":
        if t[-1] != "]":
            raise SpecError(f"unterminated list: {t[:60]}")
        return [scalar(p) for p in _split_top(t[1:-1])]
    if t[0] == "{":
        if t[-1] != "}":
            raise SpecError(f"unterminated map: {t[:60]}")
        out = {}
        for part in _split_top(t[1:-1]):
            got = _KEY.match(part)
            if not got:
                raise SpecError(f"not a key: value pair: {part[:60]}")
            out[got.group(1)] = scalar(got.group(2) or "")
        return out
    low = t.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if _INT.match(t):
        return int(t)
    if _FLOAT.match(t):
        return float(t)
    if t[0] in "&*!|>%@`":
        raise SpecError(f"YAML feature not supported in knos.yml: {t[:60]}")
    return t


def parse(text: str):
    """The subset parser: a document of block maps and block lists. Raises SpecError on anything else."""
    rows: list[list] = []
    for n, raw in enumerate(text.splitlines(), 1):
        if raw.strip() in ("---",):
            continue
        body = _strip_comment(raw).rstrip()
        if not body.strip():
            continue
        lead = body[:len(body) - len(body.lstrip())]
        if "\t" in lead:
            raise SpecError(f"line {n}: indent with spaces, not tabs")
        rows.append([len(lead), body.strip(), n])
    if not rows:
        return {}
    value, i = _block(rows, 0, rows[0][0])
    if i != len(rows):
        raise SpecError(f"line {rows[i][2]}: unexpected indentation")
    return value


def _is_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _block(rows, i, indent):
    return _list(rows, i, indent) if _is_item(rows[i][1]) else _map(rows, i, indent)


def _map(rows, i, indent):
    out: dict = {}
    while i < len(rows) and rows[i][0] == indent and not _is_item(rows[i][1]):
        got = _KEY.match(rows[i][1])
        if not got:
            raise SpecError(f"line {rows[i][2]}: expected `key: value`, found {rows[i][1][:60]!r}")
        key, rest, line = got.group(1), (got.group(2) or "").strip(), rows[i][2]
        if key in out:
            raise SpecError(f"line {line}: the key {key!r} appears twice")
        i += 1
        if rest:
            out[key] = scalar(rest)
        elif i < len(rows) and rows[i][0] > indent:
            out[key], i = _block(rows, i, rows[i][0])
        elif i < len(rows) and rows[i][0] == indent and _is_item(rows[i][1]):
            out[key], i = _list(rows, i, indent)
        else:
            out[key] = None
    if i < len(rows) and rows[i][0] > indent:
        raise SpecError(f"line {rows[i][2]}: unexpected indentation")
    return out, i


def _list(rows, i, indent):
    out: list = []
    while i < len(rows) and rows[i][0] == indent and _is_item(rows[i][1]):
        rest = rows[i][1][1:].strip()
        if not rest:
            i += 1
            if i < len(rows) and rows[i][0] > indent:
                val, i = _block(rows, i, rows[i][0])
            else:
                val = None
        elif _KEY.match(rest) and not rest.startswith(("'", '"')):
            sub = indent + (len(rows[i][1]) - len(rest))
            rows[i] = [sub, rest, rows[i][2]]
            val, i = _map(rows, i, sub)
        else:
            val, i = scalar(rest), i + 1
        out.append(val)
    return out, i


# ---- the spec ----------------------------------------------------------------------------------------------------------

def _num(v, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SpecError(f"{where} must be a number")
    return float(v)


def _command(v, where: str) -> list[str]:
    import shlex
    if isinstance(v, str) and v.strip():
        parts = shlex.split(v)
    elif isinstance(v, list) and v and all(isinstance(p, (str, int, float)) for p in v):
        parts = [str(p) for p in v]
    else:
        raise SpecError(f"{where} must be a command (text, or a list of words)")
    for p in parts:
        for name in re.findall(r"\{([^{}]*)\}", p):
            if name not in PLACEHOLDERS:
                raise SpecError(f"{where}: unknown placeholder {{{name}}}; the placeholders are " + ", ".join("{" + x + "}" for x in PLACEHOLDERS))
    return parts


def _rel(p, where: str) -> str:
    s = str(p).replace("\\", "/")
    if not s or s.startswith("/") or ".." in s.split("/") or re.match(r"^[A-Za-z]:", s):
        raise SpecError(f"{where}: {s!r} must be a path inside the repository")
    return s


def normalise(doc) -> dict:
    """The spec as Knos runs it, every default filled in. Raises SpecError naming the first thing wrong."""
    if not isinstance(doc, dict):
        raise SpecError("knos.yml must be a map of fields")
    unknown = sorted(set(doc) - {"knos", "name", "entry", "data", "splits", "claims", "compute", "seed", "authors", "funding", "description"})
    if unknown:
        raise SpecError(f"unknown field{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}")
    if doc.get("knos") != FORMAT:
        raise SpecError(f"`knos: {FORMAT}` must be the format line")
    name = doc.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
        raise SpecError("name: letters, digits, . _ - (at most 64)")
    entry = _command(doc.get("entry"), "entry")
    data = doc.get("data") or {}
    if not isinstance(data, dict) or set(data) - {"generator", "seed", "path", "protected"}:
        raise SpecError("data: a map of generator, seed, path, protected")
    generator = _command(data["generator"], "data.generator") if data.get("generator") is not None else None
    if generator is not None and not any("{data}" in p for p in generator):
        raise SpecError("data.generator must write to {data}")
    data_seed = data.get("seed", 0)
    if isinstance(data_seed, bool) or not isinstance(data_seed, int):
        raise SpecError("data.seed must be a whole number")
    protected = data.get("protected") or []
    if isinstance(protected, str):
        protected = [protected]
    protected = sorted({_rel(p, "data.protected") for p in protected} | {FILE})
    path = _rel(data["path"], "data.path") if data.get("path") else None
    splits = doc.get("splits") or {}
    if not isinstance(splits, dict) or set(splits) - {"public", "heldout"}:
        raise SpecError("splits: a map of public and heldout")
    public, heldout = str(splits.get("public", "test")), str(splits.get("heldout", "heldout"))
    claims_in = doc.get("claims")
    if not isinstance(claims_in, list) or not claims_in:
        raise SpecError("claims: a list of at least one claim")
    claims: list[dict] = []
    seen: set[str] = set()
    for k, c in enumerate(claims_in):
        where = f"claims[{k}]"
        if not isinstance(c, dict) or set(c) - {"id", "metric", "expected", "tolerance", "heldout_tolerance", "reported"}:
            raise SpecError(f"{where}: a map of id, metric, expected, tolerance, heldout_tolerance, reported")
        cid = str(c.get("id") or c.get("metric") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", cid) or cid in seen:
            raise SpecError(f"{where}: id must be unique, letters, digits, . _ -")
        seen.add(cid)
        metric = str(c.get("metric") or cid)
        tol = _num(c.get("tolerance"), f"{where}.tolerance")
        if tol < 0:
            raise SpecError(f"{where}.tolerance must not be negative")
        htol = _num(c.get("heldout_tolerance", tol), f"{where}.heldout_tolerance")
        if htol < 0:
            raise SpecError(f"{where}.heldout_tolerance must not be negative")
        rep = c.get("reported")
        if rep is not None:
            if not isinstance(rep, dict) or set(rep) != {"file", "key"}:
                raise SpecError(f"{where}.reported: {{file: <json file in the repository>, key: <its key>}}")
            rep = {"file": _rel(rep["file"], f"{where}.reported.file"), "key": str(rep["key"])}
        claims.append({"id": cid, "metric": metric, "expected": _num(c.get("expected"), f"{where}.expected"),
                       "tolerance": tol, "heldout_tolerance": htol, "reported": rep})
    if any(c["reported"] for c in claims):
        protected = sorted(set(protected) | {c["reported"]["file"] for c in claims if c["reported"]})
    compute = doc.get("compute") or {}
    if not isinstance(compute, dict) or set(compute) - {"max_seconds", "cpu_only"}:
        raise SpecError("compute: a map of max_seconds, cpu_only")
    max_seconds = compute.get("max_seconds", 600)
    if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or not 0 < max_seconds <= MAX_SECONDS:
        raise SpecError(f"compute.max_seconds must be above 0 and at most {MAX_SECONDS}")
    seed = doc.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SpecError("seed must be a whole number")
    authors = doc.get("authors") or []
    if not isinstance(authors, list) or not all(isinstance(a, dict) and set(a) <= {"github", "email", "name"} for a in authors):
        raise SpecError("authors: a list of {github, email, name}")
    funding = doc.get("funding")
    if funding is not None and not (isinstance(funding, str) and re.fullmatch(r"https://[^\s<>\"']{3,300}", funding)):
        raise SpecError("funding: one https link")
    return {"knos": FORMAT, "name": name, "description": str(doc.get("description") or ""), "entry": entry,
            "data": {"generator": generator, "seed": data_seed, "path": path, "protected": protected},
            "splits": {"public": public, "heldout": heldout}, "claims": claims,
            "compute": {"max_seconds": float(max_seconds), "cpu_only": bool(compute.get("cpu_only", True))},
            "seed": seed, "authors": authors, "funding": funding}


def load(path: Path | str) -> tuple[dict, str]:
    """(the normalised spec, sha256 of the file's bytes). `path`: knos.yml, or a folder holding one."""
    p = Path(path)
    if p.is_dir():
        p = p / FILE
    if not p.is_file():
        raise SpecError(f"no {FILE} at {p}")
    raw = p.read_bytes()
    if len(raw) > 64_000:
        raise SpecError(f"{FILE} is larger than 64 kB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SpecError(f"{FILE} is not UTF-8") from None
    return normalise(parse(text)), hashlib.sha256(raw).hexdigest()
