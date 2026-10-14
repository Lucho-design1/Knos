import io
import json

import pytest

from knos_wanted import planner


def test_deterministic_reads_category_place_audience_and_rivals():
    p = planner.deterministic("A late-night oat-milk coffee bar for students in London, rivals: Pret, Costa")
    assert p["category"] == "urn:entity:place"
    assert p["location"] == "London"
    assert p["rivals"] == ["Pret", "Costa"]
    assert "24_and_younger" in p["audience"]["age"]
    assert p["tag_queries"] and "pret" not in p["tag_queries"]
    assert p["planner"].startswith("deterministic")


def test_deterministic_defaults_and_gender():
    p = planner.deterministic("A true-crime podcast for women about art heists")
    assert p["category"] == "urn:entity:podcast"
    assert p["audience"]["gender"] == "female"
    assert p["location"] is None


def test_founder_rivals_and_place_win():
    p = planner.deterministic("Trail running shoes", rivals=["Salomon"], location="Lagos")
    assert p["rivals"] == ["Salomon"] and p["location"] == "Lagos"


def test_bad_input_refused():
    with pytest.raises(planner.PlanError):
        planner.deterministic("x")


def test_check_drops_unknown_values():
    p = planner.check({"idea": "x", "category": "urn:entity:spaceship", "proxies": ["A"],
                       "audience": {"age": ["99_plus", "25_to_29"], "gender": "other"}})
    assert p["category"] == "urn:entity:brand"
    assert p["audience"] == {"age": ["25_to_29"], "gender": None}


def _opener(content):
    def op(req, timeout=None):
        assert req.headers["Authorization"] == "Bearer k"
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(body)
    return op


def _llm_env(monkeypatch):
    monkeypatch.setenv("KNOS_WANTED_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("KNOS_WANTED_LLM_API_KEY", "k")
    monkeypatch.setenv("KNOS_WANTED_LLM_MODEL", "m")


def test_llm_planner_used_and_validated(monkeypatch):
    _llm_env(monkeypatch)
    got = json.dumps({"category": "urn:entity:brand", "proxies": ["Oatly"], "rivals": ["Alpro"], "tag_queries": ["oat milk"],
                      "audience": {"age": ["25_to_29"], "gender": None}, "location": "London"})
    p = planner.plan("oat milk ice cream", opener=_opener(got))
    assert p["planner"] == "llm (m)" and p["proxies"] == ["Oatly"] and p["location"] == "London"


def test_llm_failure_falls_back(monkeypatch):
    _llm_env(monkeypatch)
    p = planner.plan("oat milk ice cream for students", opener=_opener("not json"))
    assert p["planner"].startswith("deterministic") and "fell back" in p["planner"]
