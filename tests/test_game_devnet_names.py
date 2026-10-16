"""src/knos/game/devnet.py raised NameError at its graduation step: QUOTE had been removed while main() still read it,
and `nem` was read for a caller's own game where no Nemotron player ran. Every name the module reads must be bound."""
import ast
import builtins
from pathlib import Path

from knos.game import devnet
from knos.nebius import sources

SRC = Path(devnet.__file__)


def _bound(tree: ast.AST) -> set[str]:
    out = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
            if not isinstance(n, ast.ClassDef):
                out.update(a.arg for a in n.args.args + n.args.kwonlyargs + n.args.posonlyargs)
                out.update(a.arg for a in (n.args.vararg, n.args.kwarg) if a)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
    return out


def test_every_name_the_devnet_round_reads_is_bound():
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    bound = _bound(tree)
    read = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    assert read <= bound, sorted(read - bound)


def test_the_quote_needs_no_player_for_a_callers_own_game():
    q = devnet.quote(None, sources)
    assert q["kind"] == "compute" and q["unit_cost"] == 0.0 and "MOCK usage" in q["supplier"] and q["source"]
    assert "in nem.client.calls" not in SRC.read_text(encoding="utf-8")        # read only when a Nemotron player ran
