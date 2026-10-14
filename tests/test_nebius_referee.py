"""The models propose and explain; the referee decides. A model's words never move a verdict, and a web-found cheat
pattern becomes a rule only through the referee's own known-case test."""
from __future__ import annotations

from pathlib import Path

from knos import cheats
from knos.nebius import coder, explain, mock, rules_intake, sources
from knos.nebius.tokenfactory import TokenFactory
from knos.self import config as self_config

ROOT = Path(__file__).resolve().parents[1]


def test_the_explanation_never_changes_the_verdict():
    lenient = TokenFactory(responder=lambda m, msgs: "This change is fine and should be accepted.")
    got = explain.explain(lenient, verdict="refused", findings=[{"rule": "core_path_touched", "category": "core_path"}], subject="diff")
    assert got["verdict"] == "refused" and got["verdict_source"].startswith("Knos referee")
    assert got["advisory"] and got["explained_by"] == sources.ULTRA and got["label"] == sources.MOCK
    assert lenient.calls[0].model == sources.ULTRA


def test_the_mock_explainer_names_each_rule():
    tf = TokenFactory(responder=mock.responder())
    got = explain.explain(tf, verdict="refused", subject="x",
                          findings=[{"rule": "assertion_removed", "category": "assertion_removed", "path": "tests/t.py", "detail": "1 gone"}])
    assert "assertion_removed" in got["explanation"] and "a failure can no longer be seen" in got["explanation"]


def test_the_proposer_plugs_into_autoresearch_and_says_who_it_is():
    from knos.autoresearch.proposers import Context
    src = (ROOT / "examples" / "autoresearch" / "train.py").read_text(encoding="utf-8")
    tf = TokenFactory(responder=mock.responder())
    p = coder.NemotronProposer(tf)
    c1 = p.propose(Context("program", "idea", "train.py", src))
    assert c1.agent == "nemotron-3-super" and "features" in c1.change and c1.files["train.py"] != src
    c2 = p.propose(Context("program", "idea", "train.py", src))         # the mock's one cheat, at the second call
    assert "sealed" in c2.files["train.py"]
    from knos.autoresearch import judge
    found = judge.static_findings(c2.files, "train.py", src)
    assert {f.rule for f in found} >= {"AR-SEALED", "AR-IMPORT"}         # the referee refuses it before it runs
    assert tf.calls[0].model == sources.SUPER and tf.calls[0].mock


def test_self_coder_diffs_are_screened_by_the_referee_static_half():
    cfg = self_config.load(ROOT)
    tgt = self_config.target(cfg, "mcp-cold-start")
    tf = TokenFactory(responder=mock.responder())
    honest = coder.self_diff(tf, tgt, ROOT)
    assert honest["change"] and honest["diff"].startswith("diff --git a/src/knos/mcp.py")
    ok = coder.prescreen(honest["diff"], cfg, tgt)
    assert not ok["refused"] and ok["paths"] == ["src/knos/mcp.py"]
    cheat = coder.self_diff(tf, tgt, ROOT)
    bad = coder.prescreen(cheat["diff"], cfg, tgt)
    assert bad["refused"]
    assert {"core_path", "assertion_removed", "out_of_scope"} <= {f["category"] for f in bad["findings"]}


def _proposal(**over) -> rules_intake.RuleProposal:
    return rules_intake.RuleProposal.from_json({**mock.RULE_DRAFT, **over}, proposed_by="test")


def test_a_new_pattern_needs_its_known_cases_and_new_coverage():
    rid = "collection_hook_drops_tests_t1"
    got = rules_intake.review(_proposal(id=rid))
    assert got["accepted"] and got["fires_on_known_bad"] and not got["fires_on_known_good"]
    assert not got["library_already_refuses_bad"]                       # the library as shipped misses this case
    # a pattern that misses its own known-bad case
    assert "does not fire" in " ".join(rules_intake.review(_proposal(id=rid, pattern=r"never_matches_xyz"))["reasons"])
    # a pattern that also fires on honest code
    assert "false positive" in " ".join(rules_intake.review(_proposal(id=rid, pattern=r"return|items"))["reasons"])
    # a pattern the library already covers: redundant
    skip = ("diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n+++ b/tests/test_a.py\n"
            "@@ -1,2 +1,3 @@\n+import pytest\n+pytestmark = pytest.mark.skip\n def test_x():\n")
    red = rules_intake.review(_proposal(id=rid, pattern=r"pytest\.mark\.skip", applies_to="tests", known_bad=skip))
    assert not red["accepted"] and "redundant" in " ".join(red["reasons"]) and "skip_added" in red["already_caught_by"]
    # malformed: a bad category, a bad regex, an existing id
    assert "malformed" in rules_intake.review(_proposal(id=rid, category="made_up"))["reasons"][0]
    assert "malformed" in rules_intake.review(_proposal(id=rid, pattern="("))["reasons"][0]
    assert "exists" in rules_intake.review(_proposal(id="skip_added"))["reasons"][0]


def test_accept_registers_the_rule_and_the_library_then_refuses_the_case():
    rid = "collection_hook_drops_tests_t2"
    p = _proposal(id=rid)
    assert not cheats.refused(cheats.scan_diff(p.known_bad))
    try:
        got = rules_intake.accept(p)
        assert got["accepted"] and got["library_now_refuses_bad"] and rid in cheats.RULES
        assert not cheats.refused(cheats.scan_diff(p.known_good))
        again = rules_intake.accept(p)                                    # the library only grows: same id refused
        assert not again["accepted"] and "exists" in again["reasons"][0]
    finally:
        cheats.RULES.pop(rid, None)                                      # keep the shared registry as shipped


def test_draft_from_web_goes_through_search_then_super():
    from knos.nebius import tavily
    tf = TokenFactory(responder=mock.responder())
    tv = tavily.Tavily(responder=mock.tavily_responder)
    p, log = rules_intake.draft_from_web(tv, tf)
    assert p is not None and p.sources == ["https://mock.invalid/cheats/collection-hook"]
    assert log["mock"] and tf.calls[0].model == sources.SUPER and tv.calls[0].mock
    bad = TokenFactory(responder=lambda m, msgs: "not json")
    p2, log2 = rules_intake.draft_from_web(tv, bad)
    assert p2 is None and "not a rule proposal" in log2["error"]
