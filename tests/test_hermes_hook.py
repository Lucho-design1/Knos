"""The Hermes pre_tool_call hook (knos.hermes_plugin.pre_tool_call): with KNOS_HERMES_GUARD=block, a tool call that
would write what Knos refuses to pay for (a workflow, .knos/, the test runner's config, an existing test) is blocked
before the agent spends the work; a new test and ordinary code are not. Off by default."""
from __future__ import annotations

from knos import hermes_plugin as P


def test_off_unless_the_operator_turns_it_on(monkeypatch):
    monkeypatch.delenv("KNOS_HERMES_GUARD", raising=False)
    assert P.pre_tool_call(tool_name="write_file", args={"path": ".github/workflows/ci.yml"}) is None


def test_refused_writes_are_blocked_and_others_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("KNOS_HERMES_GUARD", "block")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_old.py").write_text("def test_x():\n    assert 1\n")
    for path, rule in ((".github/workflows/ci.yml", "workflow_edited"), (".knos/gate.yml", "sealed_tests_changed"),
                       ("tests/conftest.py", "runner_tampering"), ("tests/test_old.py", "test_edited"),
                       (str(tmp_path / "tests" / "test_old.py"), "test_edited")):
        got = P.pre_tool_call(tool_name="write_file", args={"path": path}, task_id="t", cwd=str(tmp_path))
        assert got["action"] == "block" and rule in got["message"], path
    for path in ("src/slugs.py", "tests/test_new.py", "README.md"):
        assert P.pre_tool_call(tool_name="patch", args={"file_path": path}, cwd=str(tmp_path)) is None, path
    assert P.pre_tool_call(tool_name="terminal", args={"command": "ls"}, cwd=str(tmp_path)) is None


def test_warn_never_blocks(monkeypatch, capsys):
    monkeypatch.setenv("KNOS_HERMES_GUARD", "warn")
    assert P.pre_tool_call(tool_name="write_file", args={"path": ".github/x.yml"}) is None
    assert "would get this work refused" in capsys.readouterr().err


def test_register_adds_the_hook_beside_the_tools():
    class Ctx:
        def __init__(self):
            self.tools, self.hooks = [], []

        def register_tool(self, **kw):
            self.tools.append(kw["name"])

        def register_hook(self, event, cb):
            self.hooks.append((event, cb))
    ctx = Ctx()
    P.register(ctx)
    assert "knos_verify" in ctx.tools and ctx.hooks == [("pre_tool_call", P.pre_tool_call)]

    class Old:                                    # a Hermes without hooks still gets the tools
        def __init__(self):
            self.tools = []

        def register_tool(self, **kw):
            self.tools.append(kw["name"])
    old = Old()
    P.register(old)
    assert "knos_verify" in old.tools
