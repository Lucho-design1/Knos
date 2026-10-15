"""The small part of YAML an outcome.yaml is written in, read and written without a YAML library.

Why not PyYAML: it is not a dependency of Knos, and the spec's hash must not depend on which YAML library (or which
version of one) a buyer, a seller or a CI runner has. So both sides read the file with this one reader, and the
spec's hash is taken over the canonical JSON of what it read (`knos.outcomes.spec.spec_hash`), never over the bytes.

What it reads (everything an outcome.yaml needs, nothing more):

    key: value                 a mapping; nested mappings by indentation (spaces only, no tabs)
    - value / - key: value     a sequence of scalars or of mappings
    [a, b, 1]                  a flow sequence of scalars, on one line
    'text' "text" text         strings (single quotes: '' is a quote; double quotes: \\" \\\\ \\n)
    12  -3  0.25  1e-3         numbers
    true false null ~          booleans and null
    # a comment                at the start of a line, or after a space

Anything else (anchors, tags, multi-line strings, flow mappings, documents) is refused with the line number, so a
file never means one thing here and another thing elsewhere. Any JSON object written one key per line also reads.
"""
from __future__ import annotations

import json
import re
from typing import Any

_NUM = re.compile(r"^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$")
_INT = re.compile(r"^[-+]?\d+$")
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:(\s+|$)(.*)$")


class YamlError(ValueError):
    """A line this reader does not take: the message names the line."""


def _strip_comment(text: str) -> str:
    out, q, i = [], "", 0
    while i < len(text):
        c = text[i]
        if q:
            out.append(c)
            if q == '"' and c == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if c == q:
                q = ""
        elif c in "'\"":
            q = c
            out.append(c)
        elif c == "#" and (i == 0 or text[i - 1] in " \t"):
            break
        else:
            out.append(c)
        i += 1
    return "".join(out).rstrip()


def scalar(text: str, line: int = 0) -> Any:
    """One scalar as this reader takes it."""
    t = text.strip()
    if t == "" or t in ("null", "~", "Null", "NULL"):
        return None
    if t in ("true", "True", "TRUE"):
        return True
    if t in ("false", "False", "FALSE"):
        return False
    if t[0] == "'":
        if len(t) < 2 or t[-1] != "'":
            raise YamlError(f"line {line}: an unclosed single-quoted string")
        return t[1:-1].replace("''", "'")
    if t[0] == '"':
        try:
            return json.loads(t)
        except ValueError:
            raise YamlError(f"line {line}: a double-quoted string this reader does not take") from None
    if t[0] == "[":
        if t[-1] != "]":
            raise YamlError(f"line {line}: a flow sequence must close on its line")
        inner = t[1:-1].strip()
        return [] if not inner else [scalar(part, line) for part in _split_flow(inner, line)]
    if t[0] in "{&*!|>%@`":
        raise YamlError(f"line {line}: `{t[0]}` (flow mappings, anchors, tags, block strings) is not taken; write the value plainly or quote it")
    if _INT.match(t):
        return int(t)
    if _NUM.match(t):
        return float(t)
    if ": " in t or t.endswith(":"):
        raise YamlError(f"line {line}: a plain string with `: ` in it; quote it")
    return t


def _split_flow(inner: str, line: int) -> list[str]:
    parts, cur, q = [], [], ""
    for c in inner:
        if q:
            cur.append(c)
            if c == q:
                q = ""
        elif c in "'\"":
            q = c
            cur.append(c)
        elif c == ",":
            parts.append("".join(cur))
            cur = []
        elif c in "[]{}":
            raise YamlError(f"line {line}: nested flow collections are not taken")
        else:
            cur.append(c)
    parts.append("".join(cur))
    return parts


def loads(text: str) -> Any:
    """The document in `text`: a mapping, a sequence or a scalar."""
    lines: list[tuple[int, int, str]] = []          # (line number, indent, content)
    for n, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError(f"line {n}: indent with spaces, not tabs")
        body = _strip_comment(raw)
        if not body.strip() or body.strip() in ("---", "..."):
            continue
        lines.append((n, len(body) - len(body.lstrip(" ")), body.strip()))
    if not lines:
        return None
    if lines[0][2].startswith("{"):          # a JSON object (JSON is the strict subset everybody agrees on)
        try:
            return json.loads(text)
        except ValueError as why:
            raise YamlError(f"not JSON and not the YAML this reader takes: {why}") from None
    value, i = _block(lines, 0, lines[0][1])
    if i != len(lines):
        raise YamlError(f"line {lines[i][0]}: unexpected indentation")
    return value


def _block(lines, i: int, indent: int) -> tuple[Any, int]:
    n, ind, content = lines[i]
    if ind != indent:
        raise YamlError(f"line {n}: unexpected indentation")
    if content == "-" or content.startswith("- "):
        return _seq(lines, i, indent)
    if _KEY.match(content):
        return _map(lines, i, indent)
    if i + 1 < len(lines) and lines[i + 1][1] >= indent:
        raise YamlError(f"line {n}: a scalar cannot be followed by more lines here")
    return scalar(content, n), i + 1


def _map(lines, i: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while i < len(lines):
        n, ind, content = lines[i]
        if ind < indent:
            break
        if ind > indent:
            raise YamlError(f"line {n}: unexpected indentation")
        m = _KEY.match(content)
        if not m:
            raise YamlError(f"line {n}: expected `key: value`")
        key, rest = m.group(1), m.group(3).strip()
        if key in out:
            raise YamlError(f"line {n}: the key `{key}` is written twice")
        i += 1
        if rest:
            out[key] = scalar(rest, n)
        elif i < len(lines) and (lines[i][1] > indent or (lines[i][1] == indent and lines[i][2].startswith("-"))):
            out[key], i = _block(lines, i, lines[i][1])
        else:
            out[key] = None
    return out, i


def _seq(lines, i: int, indent: int) -> tuple[list, int]:
    out: list[Any] = []
    while i < len(lines):
        n, ind, content = lines[i]
        if ind < indent or not (content == "-" or content.startswith("- ")):
            if ind == indent and not content.startswith("-"):
                break
            if ind < indent:
                break
            raise YamlError(f"line {n}: expected `- item`")
        rest = content[1:].strip()
        if not rest:
            i += 1
            if i < len(lines) and lines[i][1] > indent:
                item, i = _block(lines, i, lines[i][1])
            else:
                item = None
            out.append(item)
            continue
        if _KEY.match(rest):
            # `- key: value` starts a mapping whose keys sit two columns in
            inner = indent + (len(content) - len(rest))
            sub = [(n, inner, rest)]
            j = i + 1
            while j < len(lines) and lines[j][1] > indent:
                sub.append(lines[j])
                j += 1
            item, k = _map(sub, 0, inner)
            if k != len(sub):
                raise YamlError(f"line {sub[k][0]}: unexpected indentation")
            out.append(item)
            i = j
        else:
            out.append(scalar(rest, n))
            i += 1
    return out, i


# ---- writing ------------------------------------------------------------------------------------------------------
def _quote(s: str) -> str:
    plain = (s and not s[0].isspace() and not s[-1].isspace() and s[0] not in "-?:,[]{}#&*!|>'\"%@`~"
             and ": " not in s and " #" not in s and not s.endswith(":") and "\n" not in s)
    # what YAML 1.1 readers (PyYAML) would take as something else stays quoted: dates and times, yes/no/on/off,
    # anything starting with a digit or a sign
    yaml11 = s[:1].isdigit() or s[:1] in "+." or s.lower() in ("yes", "no", "on", "off", "y", "n", "true", "false", "null", "~")
    if plain and not yaml11 and scalar(s) == s:
        return s
    return json.dumps(s, ensure_ascii=False)


def _scalar_out(v: Any) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        r = repr(v)
        return r if ("." in r or "e" in r or "inf" in r or "nan" in r) else r + ".0"
    if isinstance(v, str):
        return _quote(v)
    raise TypeError(f"cannot write {type(v).__name__}")


def dumps(value: Any, comments: dict[str, str] | None = None) -> str:
    """`value` in the subset `loads` reads; `loads(dumps(v)) == v`. `comments`: a line of comment written above a
    top-level key."""
    lines: list[str] = []
    _emit(value, 0, lines, comments or {}, top=True)
    return "\n".join(lines) + "\n"


def _emit(v: Any, indent: int, lines: list[str], comments: dict[str, str], top: bool = False) -> None:
    pad = " " * indent
    if isinstance(v, dict):
        for k, x in v.items():
            if top and k in comments:
                lines.extend(f"# {c}" for c in comments[k].splitlines())
            if isinstance(x, dict) and x:
                lines.append(f"{pad}{k}:")
                _emit(x, indent + 2, lines, comments)
            elif isinstance(x, list) and x and any(isinstance(e, (dict, list)) for e in x):
                lines.append(f"{pad}{k}:")
                _emit(x, indent + 2, lines, comments)
            elif isinstance(x, list):
                lines.append(f"{pad}{k}: [{', '.join(_scalar_out(e) for e in x)}]")
            elif isinstance(x, dict):
                raise TypeError("an empty mapping cannot be written in this subset")
            else:
                lines.append(f"{pad}{k}: {_scalar_out(x)}")
    elif isinstance(v, list):
        for e in v:
            if isinstance(e, dict) and e:
                sub: list[str] = []
                _emit(e, indent + 2, sub, comments)
                sub[0] = f"{pad}- " + sub[0][indent + 2:]
                lines.extend(sub)
            elif isinstance(e, (dict, list)):
                raise TypeError("nested sequences are not written in this subset")
            else:
                lines.append(f"{pad}- {_scalar_out(e)}")
    else:
        lines.append(pad + _scalar_out(v))
