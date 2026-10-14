"""knos self: the archive keeps every version and its lineage; the parent is chosen by how its descendants did (HGM);
the daily merge cap holds what is over it; a rollback takes a version and its descendants off the loop branch."""
from __future__ import annotations

import pytest

from knos.self.archive import Archive
from knos.self.loop import decide


def _tree(tmp_path) -> Archive:
    a = Archive(tmp_path / "archive.json")
    a.root("c0" * 20)
    for vid, parent, decision in (("v1", "v0", "canary"), ("v2", "v1", "canary"), ("v3", "v1", "canary"),
                                  ("v4", "v0", "canary"), ("v5", "v4", "refused"), ("v6", "v4", "refused"), ("v7", "v4", "refused")):
        a.add({"id": vid, "parent": parent, "decision": decision, "target": "t", "commit": vid * 10, "metric": int(vid[1:]),
               "ts": "2026-10-13T10:00:00Z"})
    return a


def test_lineage_and_clades(tmp_path):
    a = _tree(tmp_path)
    assert a.lineage("v3") == ["v3", "v1", "v0"]
    assert a.clade("v1") == {"accepted": 2, "failed": 0, "size": 2}
    assert a.clade("v4") == {"accepted": 0, "failed": 3, "size": 3}
    assert a.clade("v0") == {"accepted": 4, "failed": 3, "size": 7}
    a.save()
    assert Archive(tmp_path / "archive.json").get("v7")["parent"] == "v4"


def test_the_parent_is_chosen_by_its_descendants_not_its_own_score(tmp_path):
    a = _tree(tmp_path)
    # v1 and v4 are both accepted; v1's children were accepted, v4's were all refused
    picks = [a.choose_parent("t", seed=s, record=False)["parent"] for s in range(400)]
    assert picks.count("v1") > 3 * picks.count("v4")
    c = a.choose_parent("t", seed=7)
    assert {d["id"] for d in c["draws"]} == {"v0", "v1", "v2", "v3", "v4"}
    assert a.choose_parent("t", seed=7, record=False)["parent"] == c["parent"]      # re-computable from the seed
    assert a.data["choices"][-1]["seed"] == 7


def test_refused_and_held_versions_are_never_parents(tmp_path):
    a = _tree(tmp_path)
    a.add({"id": "v8", "parent": "v1", "decision": "held", "target": "t", "commit": "x"})
    ids = {n["id"] for n in a.eligible("t")}
    assert "v8" not in ids and "v5" not in ids and "v1" in ids


def test_the_daily_merge_cap_holds_what_is_over_it(tmp_path):
    a = Archive(tmp_path / "a.json")
    a.root("c" * 40)
    accept = {"decision": "accept", "tiers": {"shadow": {"passed": True}}, "reasons": []}
    assert decide(dict(accept), a, 2, "2026-10-13") == ("canary", "canary")
    for i in (1, 2):
        a.add({"id": f"v{i}", "parent": "v0", "decision": "canary", "target": "t", "commit": "x", "canary_day": "2026-10-13"})
    v = dict(accept)
    assert decide(v, a, 2, "2026-10-13") == ("held", "shadow")
    assert "daily merge cap" in v["reasons"][-1]
    assert decide(dict(accept), a, 2, "2026-10-14") == ("canary", "canary")
    assert decide({"decision": "refused", "reasons": []}, a, 2, "2026-10-13") == ("refused", "sealed")


def test_an_unknown_decision_or_parent_is_refused(tmp_path):
    a = Archive(tmp_path / "a.json")
    a.root("c" * 40)
    with pytest.raises(ValueError):
        a.add({"parent": "v0", "decision": "merged"})
    with pytest.raises(KeyError):
        a.add({"parent": "v9", "decision": "canary"})
