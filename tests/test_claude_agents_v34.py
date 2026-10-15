"""Claude Agent SDK proposer with Knos's guard, Claude Managed Agents with Knos as the payer-side referee, and the
outcome draft's structured output and prompt caching. Every model answer, event and file here is a synthetic fixture
in the documented shape; no key, no network, no SDK needed."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from knos.autoresearch.proposers import Context, from_spec
from knos.claude import agent_sdk, managed
from knos.outcomes import draft


@pytest.mark.parametrize("tool,inp", [("Write", {"file_path": "tests/test_model.py"}), ("Edit", {"file_path": "/w/repo/conftest.py"}),
                                      ("Edit", {"file_path": ".github/workflows/ci.yml"}), ("Write", {"file_path": "fixtures/expected.json"}),
                                      ("Bash", {"command": "sed -i s/assert/pass/ tests/test_x.py"}), ("Write", {"file_path": "uv.lock"}),
                                      ("Write", {"file_path": ".knos/sealed.json"})])
def test_the_guard_refuses_every_write_to_the_judges_ground(tool, inp):
    deny = asyncio.run(agent_sdk.make_guard("train.py")({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": inp}, "t1", None))
    assert deny["hookSpecificOutput"]["permissionDecision"] == "deny" and deny["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_the_guard_lets_the_editable_file_change_and_nothing_else():
    g = agent_sdk.make_guard("train.py")
    assert asyncio.run(g({"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/w/repo/train.py"}}, "t", None)) == {}
    other = asyncio.run(g({"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": "/w/repo/notes.py"}}, "t", None))
    assert "only train.py" in other["hookSpecificOutput"]["permissionDecisionReason"]
    assert asyncio.run(g({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "tests/a.py"}}, "t", None)) == {}
    run_tests = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "python -m pytest -q tests/"}}
    assert asyncio.run(g(run_tests, "t", None)) == {}                      # running the tests reads them: allowed
    wipe = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "echo pass > tests/test_a.py"}}
    assert asyncio.run(g(wipe, "t", None))["hookSpecificOutput"]["permissionDecision"] == "deny"


class ResultMessage(SimpleNamespace):
    pass


def test_the_sdk_proposer_returns_the_new_file_from_the_agents_result():
    seen = {}

    async def query(prompt, options):
        seen["prompt"] = prompt
        yield SimpleNamespace(kind="assistant")
        yield ResultMessage(result="```python\n# change: lr 0.1\nCONFIG = {'lr': 0.1}\n```", session_id="sess-synthetic", total_cost_usd=0.01, is_error=False)
    p = agent_sdk.SdkProposer(cwd="/w", query=query, opts=object())
    cand = p.propose(Context(program="p", idea="i", editable="train.py", best="CONFIG = {'lr': 0.2}\n"))
    assert cand.files["train.py"].startswith("# change: lr 0.1") and cand.change == "lr 0.1" and cand.agent == "sdk:claude"
    assert "train.py" in seen["prompt"]
    assert from_spec("sdk:claude").name == "sdk:claude"


class FakeStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return iter(self.events)

    def __exit__(self, *a):
        return False


def fake_client(events, files):
    sent = []
    sessions = SimpleNamespace(create=lambda **k: {"id": "sesn_synthetic"},
                               events=SimpleNamespace(stream=lambda session_id: FakeStream(events), send=lambda session_id, events: sent.append(events)))
    beta = SimpleNamespace(sessions=sessions, files=SimpleNamespace(list=lambda scope_id, betas: {"data": files},
                                                                     download=lambda fid: SimpleNamespace(read=lambda: b"synthetic output")))
    return SimpleNamespace(beta=beta), sent


TASK = {"title": "Reproduce the claimed accuracy (synthetic)", "description": "Re-run the paper's evaluation and report accuracy.",
        "deliverable": "report.json and eval.py", "public_criteria": ["report.json has a numeric `accuracy`"], "sealed": "never sent"}
SATISFIED = [{"type": "span.outcome_evaluation_start", "iteration": 0},
             {"type": "span.outcome_evaluation_end", "result": "needs_revision", "explanation": "missing eval.py", "iteration": 0},
             {"type": "span.outcome_evaluation_end", "result": "satisfied", "explanation": "all criteria met", "iteration": 1},
             {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}}]


def test_the_platforms_satisfied_is_not_payment_knos_decides():
    client, sent = fake_client(SATISFIED, [{"id": "file_1", "filename": "report.json"}])
    refused = managed.run(client, "agent_1", "env_1", TASK, judge=lambda outs: {"accepted": False, "reasons": ["hidden re-run disagrees"]})
    assert refused.outcome == "satisfied" and not refused.payable and refused.outputs[0]["name"] == "report.json"
    ev = sent[0][0]
    assert ev["type"] == "user.define_outcome" and ev["rubric"]["type"] == "text" and "never sent" not in json.dumps(ev)
    client2, _ = fake_client(SATISFIED, [{"id": "file_1", "filename": "report.json"}])
    assert managed.run(client2, "a", "e", TASK, judge=lambda outs: {"accepted": True, "reasons": []}).payable


def test_a_session_that_never_satisfied_its_grader_is_not_even_judged():
    events = [{"type": "span.outcome_evaluation_end", "result": "max_iterations_reached", "explanation": "x"},
              {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}}]
    client, _ = fake_client(events, [])
    called = []
    r = managed.run(client, "a", "e", TASK, judge=lambda outs: called.append(1) or {"accepted": True})
    assert r.outcome == "max_iterations_reached" and not r.payable and not called
    assert managed.follow([{"type": "session.status_idle", "stop_reason": {"type": "requires_action"}}]) == (None, "", False)
    assert managed.outcome_event(TASK, max_iterations=99)["max_iterations"] == 20 and managed.agent_spec()["model"] == "claude-opus-5-5"


class FakeAnthropic:
    def __init__(self, answer: dict | None, stop="end_turn"):
        self.kwargs, self.answer, self.stop = {}, answer, stop
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.kwargs = kw
        content = [SimpleNamespace(type="text", text=json.dumps(self.answer))] if self.answer is not None else []
        return SimpleNamespace(stop_reason=self.stop, content=content)


def base_draft():
    rows = [{"ticket_id": i, "created_at": "2026-10-01T00:00:00Z", "status": "resolved" if i % 2 else "open", "escalated": 0} for i in range(30)]
    spec, _ = draft.template_draft("resolve more tickets", rows, "t.csv", "csv", synthetic=True)
    return spec, rows


def test_the_draft_asks_for_a_schema_and_caches_the_fixed_instructions():
    spec, rows = base_draft()
    answer = {"title": "Tickets resolved without a human (synthetic)", "metric_name": "resolved_without_human",
              "formula": "1 if status == 'resolved' and escalated == 0 else 0", "direction": "higher", "lift": "relative",
              "id_field": "ticket_id", "time_field": "created_at", "tier_min_lifts": [0.05, 0.1, 0.2]}
    fake = FakeAnthropic(answer)
    got = draft.llm_draft("resolve more tickets", rows, spec, key="unused", client=fake)
    kw = fake.kwargs
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["output_config"]["format"]["schema"] is draft.DRAFT_SCHEMA
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"} and kw["system"][0]["text"] == draft.SYSTEM
    assert "resolve more tickets" not in kw["system"][0]["text"] and kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default"
    assert got is not None and got["metric"]["formula"] == answer["formula"] and got["parties"] == spec["parties"] and got["escrow"] == spec["escrow"]


def test_a_refusal_or_an_answer_that_breaks_the_spec_keeps_the_template():
    spec, rows = base_draft()
    assert draft.llm_draft("g", rows, spec, key="k", client=FakeAnthropic(None, stop="refusal")) is None
    falling = {"title": "t", "metric_name": "m", "formula": "1", "direction": "higher", "lift": "relative", "id_field": "ticket_id",
               "time_field": "created_at", "tier_min_lifts": [0.2, 0.1, 0.05]}            # tiers must rise
    assert draft.llm_draft("g", rows, spec, key="k", client=FakeAnthropic(falling)) is None
    assert draft.merge_draft(spec, {"title": "only a title"}) is None
