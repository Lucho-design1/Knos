"""The sample chips' recorded cards come back from the private file at boot (SYNTHETIC cards), and a failed Qloo call
then shows the recording with its own time."""
import json

from knos_wanted import recorded


def card(idea, made):
    return {"idea": idea, "label": "LIVE Qloo data (synthetic test)", "stage": "full", "made": made, "hash": "ab" * 32,
            "calls": [{"n": 1, "call": "GET /search", "what": "search"}], "decision": {"verdict": "OPEN"}}


def test_the_recordings_file_is_read_at_boot_and_answers_when_qloo_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(recorded, "_last", {})
    f = tmp_path / "rec.json"
    chip = recorded.CHIPS[4]
    f.write_text(json.dumps({"v": 1, "cards": {recorded.key(chip): card(chip, "2026-10-22T14:09:51Z"),
                                               "not a chip": card("not a chip", "2026-10-22T00:00:00Z")}}), encoding="utf-8")
    assert recorded.load(str(f)) == 1
    failed = {"idea": chip, "calls": [{"n": 1, "error": "GET /search: HTTP 429: Qloo's rate limit"}]}
    got = recorded.honest(chip, failed)
    assert got["stale"] == {"code": 429, "from": "2026-10-22T14:09:51Z"} and got["hash"] == "ab" * 32


def test_no_file_means_no_recording_and_nothing_breaks(tmp_path, monkeypatch):
    monkeypatch.setattr(recorded, "_last", {})
    assert recorded.load(str(tmp_path / "none.json")) == 0
