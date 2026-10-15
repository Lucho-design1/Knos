"""The adapter loads the way Hermes loads it, and talks to Knos with no network.

These tests stub `agent.memory_provider` because hermes-agent is not a pip
dependency — a plugin that required the whole agent to be installed would be
exactly the coupling its CONTRIBUTING is trying to avoid. The stub mirrors the
real ABC's abstract set, so a signature drift in Hermes shows up here.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def fake_hermes(monkeypatch):
    """Stand in for `agent.memory_provider`, with the real abstract set."""
    from abc import ABC, abstractmethod

    class MemoryProvider(ABC):
        @property
        @abstractmethod
        def name(self) -> str: ...

        @abstractmethod
        def is_available(self) -> bool: ...

        @abstractmethod
        def initialize(self, session_id: str, **kwargs) -> None: ...

        @abstractmethod
        def get_tool_schemas(self) -> list: ...

    agent = types.ModuleType("agent")
    mod = types.ModuleType("agent.memory_provider")
    mod.MemoryProvider = MemoryProvider
    agent.memory_provider = mod
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.memory_provider", mod)
    yield


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "CLAUDE.md").write_text("# Rules\n\nNever use a bare except.\n", encoding="utf-8")
    (r / "src" / "auth.py").write_text("def login():\n    return True\n", encoding="utf-8")

    def git(*args):
        subprocess.run(["git", *args], cwd=str(r), check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@e")
    git("config", "user.name", "T")
    git("add", "-A")
    git("commit", "-qm", "Drop redis for sqlite: one dependency for one counter")

    monkeypatch.setenv("KNOS_HOME", str(tmp_path / "knos-home"))
    monkeypatch.chdir(r)
    from knos import paths

    paths.shared_root.cache_clear()
    paths.work_root.cache_clear()
    return r


def _provider():
    from knos_hermes.plugin import KnosMemoryProvider

    return KnosMemoryProvider()


def _point(repo):
    from knos import answer
    from knos.memory import Memory

    with Memory(repo) as mem:
        answer.point(repo, mem, index_code=False)


def test_it_satisfies_the_abc_hermes_will_load_it_against():
    """Instantiating proves every abstractmethod is implemented."""
    p = _provider()
    assert p.name == "knos"
    assert isinstance(p.get_tool_schemas(), list)


def test_register_hands_hermes_a_provider():
    """Hermes calls register(ctx) and expects register_memory_provider."""
    from knos_hermes.plugin import register

    class Ctx:
        provider = None

        def register_memory_provider(self, provider):
            self.provider = provider

    ctx = Ctx()
    register(ctx)
    assert ctx.provider is not None
    assert ctx.provider.name == "knos"


def test_the_loaders_text_scan_would_find_this_plugin():
    """Hermes decides a directory is a memory plugin by scanning the first
    8 KB of __init__.py for these names. A rename that passed every other
    test would make the plugin invisible to the loader."""
    from knos_hermes import install

    source = (install.source_dir() / "__init__.py").read_text(encoding="utf-8")[:8192]
    assert "register_memory_provider" in source or "MemoryProvider" in source


def test_recall_answers_from_the_shared_store(repo):
    _point(repo)
    p = _provider()
    p.initialize("s1")
    assert p.is_available()

    said = p.handle_tool_call("knos_recall", {"query": "why did we drop redis"})
    assert "redis" in said.lower(), said
    assert "source:" in said

    block = p.prefetch("why did we drop redis")
    assert "Knos" in block and "redis" in block.lower()


def test_remember_then_recall_across_a_fresh_provider(repo):
    _point(repo)
    first = _provider()
    first.initialize("s1")
    first.handle_tool_call(
        "knos_remember", {"fact": "we picked sqlite over redis", "about": "storage"}
    )

    # A different provider instance, as a later Hermes session would be.
    second = _provider()
    second.initialize("s2")
    said = second.handle_tool_call("knos_recall", {"query": "storage sqlite"})
    assert "sqlite over redis" in said, said


def test_a_claim_by_another_agent_is_withheld_from_hermes(repo):
    from datetime import datetime, timezone

    from knos.memory import Memory

    _point(repo)
    with Memory(repo) as mem:
        mem.working_on(
            "the auth refactor", "Claude Code", datetime.now(timezone.utc).isoformat()
        )

    p = _provider()
    p.initialize("s1")
    said = p.handle_tool_call("knos_recall", {"query": "the auth refactor"})
    assert said.startswith("Withheld."), said
    assert "Claude Code" in said


def test_hermes_claims_and_releases(repo):
    from knos.memory import Memory

    _point(repo)
    p = _provider()
    p.initialize("s1")
    assert "Claimed" in p.handle_tool_call("knos_claim", {"work": "the parser"})
    with Memory(repo) as mem:
        assert [w["topic"] for w in mem.claims()] == ["the parser"]

    # Hermes is not withheld from its own claim.
    mine = p.handle_tool_call("knos_recall", {"query": "the parser"})
    assert not mine.startswith("Withheld.")

    p.handle_tool_call("knos_done", {})
    with Memory(repo) as mem:
        assert mem.claims() == []


def test_shutdown_releases_what_this_session_held(repo):
    from knos.memory import Memory

    _point(repo)
    p = _provider()
    p.initialize("s1")
    p.handle_tool_call("knos_claim", {"work": "the parser"})
    p.shutdown()
    with Memory(repo) as mem:
        assert mem.claims() == [], "left other agents blocked after exit"


def test_outside_a_repo_it_says_so_rather_than_failing(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOS_HOME", str(tmp_path / "h"))
    monkeypatch.chdir(tmp_path)
    from knos import paths

    paths.shared_root.cache_clear()
    paths.work_root.cache_clear()
    p = _provider()
    assert p.is_available() is False
    assert "not in a git repo" in p.handle_tool_call("knos_recall", {"query": "x"})


def test_nothing_touches_the_network(repo, monkeypatch):
    """Every other Hermes memory provider needs an API key. This one must not
    open a socket at all."""

    class Blocked(AssertionError):
        pass

    def refuse(*a, **k):
        raise Blocked("the adapter opened a network connection")

    _point(repo)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "bind", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    p = _provider()
    p.initialize("s1")
    p.prefetch("redis")
    p.handle_tool_call("knos_recall", {"query": "redis"})
    p.handle_tool_call("knos_remember", {"fact": "local only", "about": "net"})
    p.handle_tool_call("knos_claim", {"work": "the parser"})
    p.handle_tool_call("knos_done", {})
    p.shutdown()


def test_install_puts_it_where_hermes_scans(tmp_path):
    from knos_hermes import install

    target = install.install(target_home=tmp_path)
    assert target == tmp_path / "plugins" / "knos"
    assert (target / "__init__.py").exists()

    # Idempotent: installing twice must not fail or nest a copy inside itself.
    again = install.install(target_home=tmp_path)
    assert again == target
    assert not (target / "plugin").exists()


def test_install_honours_hermes_home(tmp_path, monkeypatch):
    from knos_hermes import install

    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "custom"))
    assert install.hermes_home() == tmp_path / "custom"


def test_the_plugin_yaml_hermes_reads_ships_and_installs(tmp_path):
    """Hermes reads plugin.yaml for the name shown in `hermes memory setup`.
    Without it the provider lists with an empty description."""
    import yaml

    from knos_hermes import install

    target = install.install(target_home=tmp_path)
    meta_file = target / "plugin.yaml"
    assert meta_file.exists(), "plugin.yaml did not reach the install target"
    meta = yaml.safe_load(meta_file.read_text(encoding="utf-8-sig"))
    assert meta["name"] == "knos"
    assert meta["description"].strip()
    assert not (target / "__pycache__").exists()
