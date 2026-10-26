"""A paper crossed on this server lately is answered from that crossing at once, said so in its steps; one that met a
Qloo outage is crossed again unless Qloo's pause still holds. SYNTHETIC jobs only; nothing asks Qloo."""
import time

from knos_wanted import agent, qloo_rest


class State:
    def __init__(self, reports):
        self.reports = reports

    def report(self, h):
        return self.reports.get(h)


def _job(i, report, started):
    return {"id": f"j{i}", "ref": "10.1038/x", "idea": None, "place": None, "product": None, "leader": None, "options": {},
            "status": "done", "steps": [{"title": "read the paper"}], "started": started, "report": report, "card": None}


def test_a_paper_crossed_lately_is_answered_from_that_crossing(monkeypatch):
    monkeypatch.setattr(agent, "JOBS", {"j1": _job(1, "r1", time.time() - 60)})
    monkeypatch.setitem(qloo_rest._hold, "until", 0.0)
    job = agent.start(State({"r1": {"hash": "r1"}}), ref="10.1038/x")
    assert job["status"] == "done" and job["report"] == "r1" and job["kept_from"] == "j1" and job["steps"][-1]["title"].startswith("kept from")


def test_an_outage_is_crossed_again_unless_the_pause_holds(monkeypatch):
    started = []
    monkeypatch.setattr(agent, "run", lambda job, state: started.append(job["id"]))
    monkeypatch.setattr(agent, "JOBS", {"j1": _job(1, "r1", time.time() - 60)})
    st = State({"r1": {"hash": "r1", "qloo_down": {"code": 429}}})
    monkeypatch.setitem(qloo_rest._hold, "until", 0.0)
    assert agent.start(st, ref="10.1038/x", wait=False)["status"] == "running"
    monkeypatch.setitem(qloo_rest._hold, "until", time.time() + 300)
    assert agent.start(st, ref="10.1038/x")["kept_from"] == "j1"


def test_an_old_crossing_is_not_kept(monkeypatch):
    monkeypatch.setattr(agent, "run", lambda job, state: None)
    monkeypatch.setattr(agent, "JOBS", {"j1": _job(1, "r1", time.time() - agent.KEEP_CROSSING_S - 1)})
    assert "kept_from" not in agent.start(State({"r1": {"hash": "r1"}}), ref="10.1038/x")
