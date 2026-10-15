"""Leitner re-verification: pass promotes, fail demotes to box 1 and pauses payout; the schedule matches the config;
sealed tests rotate; the cost per verification drops on a SYNTHETIC history (labelled synthetic)."""
from __future__ import annotations

from pathlib import Path

import pytest

from knos import leitner
from knos.leitner import DAY, Scheduler

ROOT = Path(__file__).resolve().parents[1]


def test_the_config_file_is_valid_and_matches_the_built_in_default():
    cfg = leitner.load_config(ROOT / "config" / "leitner.yaml")
    assert cfg["default"]["boxes"] == leitner.DEFAULT["default"]["boxes"] == [1, 3, 7, 30]
    assert leitner.schedule(cfg, "lab")["unit"] == "orders"
    assert leitner.validate({"default": {"unit": "weeks", "boxes": [3, 1]}}) == ["default.unit: days or orders",
                                                                                "default.boxes: a rising list of whole numbers from 1"]


def test_pass_promotes_up_the_boxes_on_the_configured_schedule():
    s = Scheduler(leitner.load_config(), {}, None)
    kind = leitner.KINDS[0]
    it = s.add("claim:1", kind, 0)
    assert it.box_number == 1 and it.next_due == 1 * DAY
    for want_box, want_gap in ((2, 3), (3, 7), (4, 30), (4, 30)):
        now = it.next_due
        s.result("claim:1", True, now)
        assert it.box_number == want_box and it.next_due == now + want_gap * DAY
    assert s.can_pay("claim:1")


def test_a_failure_drops_to_box_1_and_pauses_payouts_until_it_passes_again():
    s = Scheduler(leitner.load_config(), {}, None)
    s.add("product:x", "product", 0)
    for d in (1, 4, 11):
        s.result("product:x", True, d * DAY)
    s.result("product:x", False, 41 * DAY)
    it = s.items["product:x"]
    assert it.box_number == 1 and it.paused and not s.can_pay("product:x") and it.next_due == 42 * DAY
    assert s.due(42 * DAY)[0].id == "product:x"
    s.result("product:x", True, 42 * DAY)
    assert s.can_pay("product:x") and it.box_number == 1          # back to paying, starting again from box 1
    s.result("product:x", True, 43 * DAY)
    assert it.box_number == 2
    assert not s.can_pay("unknown")


def test_labs_are_counted_in_orders_new_labs_every_order_proven_labs_rarely():
    s = Scheduler(leitner.load_config(), {}, None)
    s.add("lab:a", "lab", 0)
    assert s.due_orders("lab:a", 1)
    n = 1
    for _ in range(4):
        s.result("lab:a", True, n)
        n = s.items["lab:a"].next_due
    assert s.items["lab:a"].box_number == 4 and not s.due_orders("lab:a", n - 1) and s.due_orders("lab:a", n)
    s.result("lab:a", False, n)
    assert s.due_orders("lab:a", n + 1) and not s.can_pay("lab:a")


def test_state_survives_a_restart(tmp_path):
    s = Scheduler.load(tmp_path / "state.json")
    s.add("agent:7", "agent", 0)
    s.result("agent:7", False, DAY)
    s.save()
    again = Scheduler.load(tmp_path / "state.json")
    assert again.items["agent:7"].paused and not again.can_pay("agent:7")


def test_sealed_tests_nobody_fails_rotate_out_and_tests_that_catch_cheats_stay_hot():
    tests = [{"id": "t-clean", "runs": 25, "failures": 0}, {"id": "t-young", "runs": 3, "failures": 0},
             {"id": "t-catcher", "runs": 40, "failures": 2, "cheats_caught": 1, "runs_since_catch": 2},
             {"id": "t-old-catch", "runs": 60, "failures": 1, "cheats_caught": 1, "runs_since_catch": 30}]
    got = leitner.rotate(tests, [{"id": "t-new-1"}, {"id": "t-new-2"}])
    assert got["retired"] == ["t-clean"] and got["added"] == ["t-new-1"] and got["hot"] == ["t-catcher"]
    assert set(got["keep"]) == {"t-young", "t-catcher", "t-old-catch", "t-new-1"}


def test_cost_per_verification_drops_on_a_synthetic_history_labelled_synthetic():
    d = leitner.dashboard()
    assert d["synthetic"] is True and d["label"].startswith("SYNTHETIC")
    assert d["after"]["reruns_per_item_day"] < d["before"]["reruns_per_item_day"]
    assert d["before"]["reruns_per_item_day"] == 1.0                 # daily: every item, every day
    assert d["after"]["caught"] == d["before"]["caught"] == d["before"]["breakages"]   # every breakage still caught
    assert 0 < d["reruns_saved_share"] < 1
    assert leitner.dashboard() == d                                   # seeded: the same every time
    assert "USD" not in str(d["unit"])                                # no unmeasured price is shown
