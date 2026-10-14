"""knos.yml: the strict YAML subset parser and the spec's rules (knos.repro.spec)."""
from __future__ import annotations

import pytest

from knos.repro import example, spec as sp


def test_the_subset_parser_reads_maps_lists_lists_of_maps_and_scalars():
    text = """# a comment
knos: 1
name: demo   # trailing comment
entry: python train.py --out {out}
data:
  protected: [data/, "a b.json"]
claims:
  - id: acc
    expected: 0.9
    tolerance: 1e-2
    reported: {file: r.json, key: acc}
  - id: loss
    expected: -3
    tolerance: 0
funding: https://example.org/x#y
flags:
- true
- null
- 'it''s'
"""
    got = sp.parse(text)
    assert got["knos"] == 1 and got["name"] == "demo" and got["entry"] == "python train.py --out {out}"
    assert got["data"] == {"protected": ["data/", "a b.json"]}
    assert got["claims"][0] == {"id": "acc", "expected": 0.9, "tolerance": 0.01, "reported": {"file": "r.json", "key": "acc"}}
    assert got["claims"][1]["expected"] == -3 and got["funding"] == "https://example.org/x#y"
    assert got["flags"] == [True, None, "it's"]


def test_the_parser_agrees_with_pyyaml_on_the_example():
    yaml = pytest.importorskip("yaml")
    text = example.SPEC.format(expected=example.HONEST)
    assert sp.parse(text) == yaml.safe_load(text)


@pytest.mark.parametrize("text, words", [
    ("a: 1\na: 2\n", "appears twice"),
    ("a:\n\tb: 1\n", "tabs"),
    ("a: &anchor 1\n", "not supported"),
    ("a: 1\n   b: 2\n", "indentation"),
    ("a: 'open\n", "unterminated"),
])
def test_the_parser_refuses_what_it_does_not_know(text, words):
    with pytest.raises(sp.SpecError, match=words):
        sp.parse(text)


def _doc(**over):
    doc = sp.parse(example.SPEC.format(expected=0.8))
    doc.update(over)
    return doc


def test_the_example_normalises_with_defaults_and_protects_the_spec_and_the_results_file():
    s = sp.normalise(_doc())
    assert s["name"] == "synthetic-centroid" and s["entry"][:2] == ["python", "train.py"]
    assert s["data"]["protected"] == ["knos.yml", "results.json"]
    assert s["claims"][0]["tolerance"] == 0.02 and s["claims"][0]["heldout_tolerance"] == 0.07
    assert s["compute"]["max_seconds"] == 600.0 and s["funding"] is None


@pytest.mark.parametrize("over, words", [
    ({"knos": 2}, "format line"),
    ({"name": "bad name"}, "name"),
    ({"entry": "python x.py {nope}"}, "unknown placeholder"),
    ({"claims": []}, "at least one claim"),
    ({"claims": [{"id": "a", "expected": "high", "tolerance": 0.1}]}, "expected must be a number"),
    ({"claims": [{"id": "a", "expected": 1, "tolerance": -1}]}, "not be negative"),
    ({"claims": [{"id": "a", "expected": 1, "tolerance": 0}, {"id": "a", "expected": 1, "tolerance": 0}]}, "unique"),
    ({"compute": {"max_seconds": 10**9}}, "max_seconds"),
    ({"funding": "http://insecure"}, "https"),
    ({"data": {"protected": ["../outside"]}}, "inside the repository"),
    ({"surprise": 1}, "unknown field"),
])
def test_the_spec_refuses_each_wrong_field(over, words):
    with pytest.raises(sp.SpecError, match=words):
        sp.normalise(_doc(**over))


def test_load_hashes_the_file_bytes(tmp_path):
    example.write(tmp_path)
    s, sha = sp.load(tmp_path)
    import hashlib
    assert sha == hashlib.sha256((tmp_path / "knos.yml").read_bytes()).hexdigest() and s["claims"][0]["expected"] == example.HONEST
    with pytest.raises(sp.SpecError, match="no knos.yml"):
        sp.load(tmp_path / "nowhere")
