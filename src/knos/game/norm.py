"""How the game tells a copy from new work: a file's program with comments, spacing and docstrings set aside."""
from __future__ import annotations

import ast
import hashlib


def normalized_sha256(text: str) -> str:
    """The hash duplicates are compared by: for Python, the AST dump with docstrings and bare strings dropped (so
    comments, blank lines, spacing and quotes do not make a copy new); otherwise the text without '#' comments, blank
    lines and whitespace."""
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list):
                body[:] = [b for b in body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                                                   and isinstance(b.value.value, str))] or [ast.Pass()]
        return hashlib.sha256(("py:" + ast.dump(tree, annotate_fields=False, include_attributes=False)).encode()).hexdigest()
    except (SyntaxError, ValueError, RecursionError):
        lines = [ln.split("#", 1)[0] for ln in text.splitlines()]
        return hashlib.sha256(("txt:" + "".join("".join(ln.split()) for ln in lines)).encode()).hexdigest()
