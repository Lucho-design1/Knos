"""An agent limited to Knos's tools can read the round's baseline and README: the open round's submit block carries
both as text (CHAMPION3 E3: an MCP-only agent wrote train.py blind and every attempt scored "shown": null)."""
from pathlib import Path

from knos_wanted import tasks

ROOT = Path(__file__).resolve().parents[3]


class FakeTools:
    def call(self, name, args):
        if name == "knos_game_state":
            return {"game": {"id": "knos-demo-test", "title": "Demo round", "status": "open", "round": 1}}
        return {"board": []}


def test_the_open_round_carries_the_baseline_and_the_readme_as_text(monkeypatch):
    monkeypatch.setattr(tasks, "available", lambda: (True, ""))
    monkeypatch.setattr(tasks, "_tools", lambda: FakeTools())
    (r,) = tasks.rounds()
    sub = r["submit"]
    assert sub["baseline_source"] == (ROOT / "examples" / "autoresearch" / "train.py").read_text(encoding="utf-8")
    assert sub["readme_text"] == (ROOT / "examples" / "autoresearch" / "README.md").read_text(encoding="utf-8")
    assert "def " in sub["baseline_source"]
