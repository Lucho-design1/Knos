"""The front door's counter is a weekly trend of outside use only: "<n> ideas checked this week, up from <m> last
week", shown when n > m and n >= 10, else nothing. Test sessions (the flag knos_wanted.outside reads) and automated
clients are left out of the days it counts."""
import datetime as dt

from knos_wanted import auth, outside, usage


def test_the_line_shows_only_for_real_growth_from_ten():
    assert usage.trend_line(12, 5) == "12 ideas checked this week, up from 5 last week"
    assert usage.trend_line(4, 1) is None
    assert usage.trend_line(12, 15) is None


def test_this_week_and_the_week_before_are_counted_from_the_days():
    today = dt.date(2026, 10, 25)
    days = {(today - dt.timedelta(days=i)).isoformat(): {"checks": c, "briefs": 0}
            for i, c in [(0, 4), (3, 5), (6, 3), (7, 2), (13, 3), (14, 9)]}
    assert usage.week_counts(days, today) == (12, 5)
    assert usage.trend_line(*usage.week_counts(days, today)) == "12 ideas checked this week, up from 5 last week"


def test_a_test_session_and_an_automated_client_are_left_out(monkeypatch, tmp_path):
    monkeypatch.setenv("KNOS_WANTED_STATE", str(tmp_path))
    browser = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    for label, agent, counted in (("Knos test run", browser, 0), ("someone", browser, 1), ("someone", "python-urllib/3.12", 0)):
        tok = auth.guest(label)["token"]
        outside.CTX.headers = {"User-Agent": agent, "Authorization": "Bearer " + tok}
        before = sum(v["checks"] for v in (usage._doc().get("days") or {}).values())
        usage.bump(checks=1)
        after = sum(v["checks"] for v in (usage._doc().get("days") or {}).values())
        assert after - before == counted, (label, agent)
    outside.CTX.headers = None
