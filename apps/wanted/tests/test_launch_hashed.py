"""A project opened from a brief whose money terms Qloo set keeps the launch block, and its criteria hash is the brief's
own (knos.ready.criteria_hash): the city and the pre-order target cannot change without the hash changing."""
from knos import ready
from knos_wanted import metros, valley

T = {"city": "Boulder, CO", "cbsa": "14500", "affinity": 0.9986, "cells": 3, "population": 326831, "target": 10,
     "refund_rule": metros.REFUND.format(target=10, city="Boulder, CO")}


def test_the_launch_terms_are_kept_and_hashed_with_the_milestones():
    b = metros.brief("a synthetic jacket", T)
    out = valley.create_project({"sub": "u1", "label": "test"}, "custom", b["title"], brief=b)
    p = valley.project(out["id"])
    assert p["launch"]["city"] == "Boulder, CO" and p["launch"]["target"] == 10 and out["launch"] == p["launch"]
    assert valley.readiness(p)["criteria_hash"] == ready.criteria_hash(b)
    moved = metros.brief("a synthetic jacket", {**T, "target": 11})
    assert ready.criteria_hash(moved) != ready.criteria_hash(b)
