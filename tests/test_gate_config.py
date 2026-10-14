""".knos/gate.yml: the schema, the loader with and without PyYAML, defaults, and every refusal it names."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from knos.gate import config

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
FULL = f"""
version: 1   # the only version
hidden_tests:
  source: secret
  secret: KNOS_GATE_HIDDEN
  sha256: {SHA}
  into: tests/hidden
  command: "python -m pytest -q tests/hidden"
  timeout: 300
public_tests:
  command: python -m pytest -q tests
setup: python -m pip install pytest
scope:
  allow: ["src/**", "*.py"]
  deny:
    - docs/**
protect: [data/**]
on_fail: close
label: knos-gate-failed
pass_label: knos-verified
outside_only: false
receipt: true
bounties:
  enabled: true
  cluster: devnet
  mint: 4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU
"""


def test_full_config_loads_with_defaults_filled():
    cfg = config.loads(FULL)
    assert cfg["hidden_tests"]["sha256"] == SHA and cfg["hidden_tests"]["timeout"] == 300
    assert cfg["scope"]["allow"] == ["src/**", "*.py"]
    assert cfg["scope"]["deny"][:2] == [".github/**", ".knos/**"] and "docs/**" in cfg["scope"]["deny"]
    assert cfg["on_fail"] == "close" and cfg["pass_label"] == "knos-verified" and cfg["outside_only"] is False
    assert cfg["bounties"]["enabled"] is True and cfg["setup"] == "python -m pip install pytest"


def test_the_reader_without_pyyaml_reads_the_same():
    yaml = pytest.importorskip("yaml")
    assert config.mini_yaml(FULL) == yaml.safe_load(FULL)


def test_minimal_public_only_config():
    cfg = config.loads("version: 1\npublic_tests:\n  command: pytest\n")
    assert cfg["hidden_tests"] is None and cfg["on_fail"] == "comment" and cfg["outside_only"] is True
    assert cfg["scope"] == {"allow": [], "deny": [".github/**", ".knos/**"]}


@pytest.mark.parametrize("text, said", [
    ("version: 2\npublic_tests: {command: x}", "version"),
    ("version: 1", "neither hidden_tests nor public_tests"),
    ("version: 1\nhidden_tests:\n  sha256: abc\n  command: x\n", "hidden_tests.sha256"),
    (f"version: 1\nhidden_tests:\n  source: repo\n  repo: a/b\n  ref: main\n  sha256: {SHA}\n  command: x\n", "pinned commit"),
    (f"version: 1\nhidden_tests:\n  sha256: {SHA}\n  command: x\n  into: ../up\n", "hidden_tests.into"),
    ("version: 1\npublic_tests:\n  command: x\nunknown: 1\n", "unknown key `unknown`"),
    ("version: 1\npublic_tests:\n  command: x\non_fail: explode\n", "on_fail"),
    ("version: 1\npublic_tests:\n  command: x\nscope:\n  allow: [/etc/**]\n", "relative"),
    ("version: 1\npublic_tests:\n  command: x\nbounties:\n  cluster: mainnet\n", "no mainnet"),
])
def test_refusals_name_the_problem(text, said):
    with pytest.raises(config.ConfigError) as e:
        config.loads(text)
    assert said in str(e.value)


def test_mini_yaml_refuses_what_it_does_not_read():
    with pytest.raises(config.ConfigError):
        config.mini_yaml("a:\n\tb: 1\n")
    with pytest.raises(config.ConfigError):
        config.mini_yaml("a: 1\na: 2\n")


def test_load_reads_the_base_tree(tmp_path):
    with pytest.raises(config.ConfigError, match="not set up"):
        config.load(tmp_path)
    (tmp_path / ".knos").mkdir()
    (tmp_path / ".knos" / "gate.yml").write_text(FULL, encoding="utf-8")
    assert config.load(tmp_path)["hidden_tests"]["into"] == "tests/hidden"


def test_the_published_schema_is_the_code_schema():
    on_disk = json.loads((ROOT / "src" / "knos" / "gate" / "gate.schema.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(config.SCHEMA))


def test_the_example_config_is_valid():
    cfg = config.load(ROOT / "actions" / "gate" / "example")
    assert cfg["hidden_tests"]["command"]
