"""The metric's formula: one row's fields in, one number out, and nothing else evaluated.

A formula is a Python-like expression read with `ast` and walked here; it is never passed to eval. It may use the
row's field names, numbers, strings, True/False/None, comparisons (chained too), `and`/`or`/`not`, + - * / // % and
unary minus, `x if c else y`, `x in (a, b)`, and the functions abs, min, max, float, int, len, round. No attribute,
no subscript, no call to anything else, no comprehension, no lambda. A field the row lacks is an error that names it.

CSV values arrive as text: a field that reads as a whole number or a decimal is taken as that number, "true"/"false"
as booleans, "" as None (`row_values`), so `reopened == 0` and `minutes < 30` mean what they say.
"""
from __future__ import annotations

import ast
import operator
import re
from typing import Any, Callable

_NUM = re.compile(r"^-?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$")
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
_FUNCS: dict[str, Callable] = {"abs": abs, "min": min, "max": max, "float": float, "int": int, "len": len, "round": round}


class FormulaError(ValueError):
    """The formula uses something this reader does not evaluate, or a row lacks a field it names."""


def _check(node: ast.AST) -> None:
    for n in ast.walk(node):
        if isinstance(n, (ast.Expression, ast.Load, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd, ast.BinOp,
                          ast.Compare, ast.IfExp, ast.Name, ast.Constant, ast.Tuple, ast.List, ast.Call, *_BIN, *_CMP)):
            if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords):
                raise FormulaError("only abs, min, max, float, int, len and round may be called")
            if isinstance(n, ast.Name) and n.id.startswith("__"):
                raise FormulaError(f"the name {n.id} is not taken")
            continue
        raise FormulaError(f"`{type(n).__name__}` is not taken in a formula")


def compile_formula(text: str) -> ast.Expression:
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as why:
        raise FormulaError(f"not an expression: {why.msg}") from None
    _check(tree)
    return tree


def fields(text: str) -> list[str]:
    """The field names a formula reads, in order of first use."""
    seen: list[str] = []
    for n in ast.walk(compile_formula(text)):
        if isinstance(n, ast.Name) and n.id not in _FUNCS and n.id not in seen and n.id not in ("True", "False", "None"):
            seen.append(n.id)
    return seen


def _eval(n: ast.AST, row: dict) -> Any:
    if isinstance(n, ast.Expression):
        return _eval(n.body, row)
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Name):
        if n.id in row:
            return row[n.id]
        raise FormulaError(f"the row has no field `{n.id}`")
    if isinstance(n, ast.BoolOp):
        if isinstance(n.op, ast.And):
            v: Any = True
            for x in n.values:
                v = _eval(x, row)
                if not v:
                    return v
            return v
        v = False
        for x in n.values:
            v = _eval(x, row)
            if v:
                return v
        return v
    if isinstance(n, ast.UnaryOp):
        v = _eval(n.operand, row)
        return (not v) if isinstance(n.op, ast.Not) else (-v if isinstance(n.op, ast.USub) else +v)
    if isinstance(n, ast.BinOp):
        return _BIN[type(n.op)](_eval(n.left, row), _eval(n.right, row))
    if isinstance(n, ast.Compare):
        left = _eval(n.left, row)
        for op, right_node in zip(n.ops, n.comparators):
            right = _eval(right_node, row)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(n, ast.IfExp):
        return _eval(n.body, row) if _eval(n.test, row) else _eval(n.orelse, row)
    if isinstance(n, (ast.Tuple, ast.List)):
        return tuple(_eval(e, row) for e in n.elts)
    if isinstance(n, ast.Call):
        return _FUNCS[n.func.id](*(_eval(a, row) for a in n.args))      # type: ignore[attr-defined]
    raise FormulaError(f"`{type(n).__name__}` is not taken in a formula")


def value(text_or_tree: str | ast.Expression, row: dict) -> float:
    """The formula's number for one row (booleans count as 1 and 0)."""
    tree = compile_formula(text_or_tree) if isinstance(text_or_tree, str) else text_or_tree
    v = _eval(tree, row)
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if not isinstance(v, (int, float)):
        raise FormulaError(f"the formula gave {v!r}, not a number")
    return float(v)


def row_values(row: dict) -> dict:
    """A CSV row's text as numbers, booleans and None where it reads as one."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, str):
            t = v.strip()
            if t == "":
                out[k] = None
            elif t.lower() in ("true", "false"):
                out[k] = t.lower() == "true"
            elif _NUM.match(t):
                out[k] = int(t) if re.fullmatch(r"-?\d+", t) else float(t)
            else:
                out[k] = t
        else:
            out[k] = v
    return out


def lift(treated: float, control: float, kind: str, direction: str) -> float:
    """How much better treated is than control. relative: (t - c) / c (for `lower`, (c - t) / c); absolute: t - c
    (for `lower`, c - t). A relative lift over a control of 0 is refused: it has no size."""
    diff = (treated - control) if direction == "higher" else (control - treated)
    if kind == "absolute":
        return diff
    if control == 0:
        raise ValueError("the control group's metric is 0, so a relative lift has no size; use lift: absolute")
    return diff / abs(control)
