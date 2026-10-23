"""TASK-WORLD T11 test_science_briefs: real research passes the Ready check. Lab, field and clinical milestones may run
to 1,095 days (held in tranches of at most 90 days, the longest an order holds money); a count on a named standard or
registry, or an effect size in SD, is a measurable target; a verifier's check may use normal punctuation. What was not
measurable before still is not."""
from knos import ready


def ms(target, check="Third-party lab certificate", days=60, name="Step"):
    return {"milestones": [{"name": name, "target": target, "verifier": {"check": check}, "deadline_days": days}]}


def test_counts_on_named_standards_registries_and_effect_sizes_are_measurable():
    for t in ("1 pass on ASTM C1157 Type GU", "1 pass on IEC 61215:2021 and IEC 61730", "8 of 8 tests passed on UN 38.3",
              "0 WHO GDWQ guideline exceedances on an ISO/IEC 17025 potability panel", "0.20 SD English gain on the endline test",
              "1 registered pre-analysis plan on the AEA RCT Registry", "1 preregistered protocol on ClinicalTrials.gov"):
        assert ready.check(ms(t))["ready"], t
    for t in ("pass review", "signed-off spec doc", "all reports render correctly", "a better cement"):
        assert not ready.check(ms(t))["ready"], t


def test_lab_field_and_clinical_work_runs_to_1095_days_in_90_day_tranches():
    assert ready.check(ms("1 pass on IEC 61215:2021", days=300))["ready"]
    assert ready.check(ms("95 percent of control yield on a 3-site field trial", days=1_095))["ready"]
    assert not ready.check(ms("1 pass on IEC 61215:2021", days=1_096))["ready"]
    assert not ready.check(ms("p95 under 300 ms", check="test_latency", days=91))["ready"]        # software keeps 90 days
    # a research brief's other milestones are paced by its trial
    brief = {"milestones": [ms("1 pass on ASTM C1157 Type GU", days=300)["milestones"][0],
                            {"name": "Cost", "target": "10 USD per student per term", "verifier": {"check": "Costing sheet totals reproduce"},
                             "deadline_days": 200, "key": "cost"}]}
    assert ready.check(brief)["ready"]
    assert ready.tranches(365 * 86_400) == [90 * 86_400] * 4 + [5 * 86_400] and ready.tranches(30 * 86_400) == [30 * 86_400]


def test_a_check_may_use_normal_punctuation_but_no_backticks_or_control_characters():
    assert ready.check(ms("12 samples", check="Lab report: n of at least 4 per arm, p<0.05; 95% CI, the 'BNI' line"))["ready"]
    assert not ready.check(ms("12 samples", check="run `rm -rf`"))["ready"]
    assert not ready.check(ms("12 samples", check="a bell\x07 in it"))["ready"]
