"""knos.verify.policy: a repository's AI policy, read from its own files, decides whether an agent may open a pull
request there. Banned is never overridable; conditional needs a person; the strictest sentence wins; the policy's
words come back only inside `untrusted`."""

from __future__ import annotations

import pytest

from knos.verify import policy


@pytest.mark.parametrize("sentence, stance", [
    ("We do not accept AI-generated pull requests.", "banned"),
    ("Pull requests written by ChatGPT, Copilot or Claude will be closed.", "banned"),
    ("AI-generated contributions are banned.", "banned"),
    ("Do not submit code produced by LLMs.", "banned"),
    ("AI-assisted pull requests without human review will be closed.", "conditional"),
    ("Fully autonomous coding agents are not welcome unless a human has tested the change.", "conditional"),
    ("AI-generated pull requests without disclosure will be closed.", "disclose"),
    ("AI-assisted contributions must be disclosed in the pull request description.", "disclose"),
    ("If you used an AI tool, mention it.", "disclose"),
    ("AI tools are welcome here.", "allowed"),
    ("Please run the tests before you open a pull request.", None),
])
def test_one_sentence_is_placed_in_one_stance(sentence, stance):
    assert policy.stance_of(sentence) == stance


def test_the_strictest_sentence_wins_and_its_words_are_returned_as_untrusted_data(tmp_path):
    (tmp_path / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nAI tools are welcome for drafting.\n\nHowever, we do not accept AI-generated pull requests.\n", encoding="utf-8")
    got = policy.read(tmp_path)
    assert got["stance"] == "banned" and got["file"] == "CONTRIBUTING.md" and got["source"] == "prose"
    assert got["untrusted"]["lines"] == ["However, we do not accept AI-generated pull requests."]
    assert not policy.may_open_pr("banned") and not policy.may_open_pr("banned", human_confirmed=True)


def test_ai_policy_md_comes_before_contributing_and_a_marker_line_wins_over_prose(tmp_path):
    (tmp_path / "CONTRIBUTING.md").write_text("AI-generated code is not accepted.\n", encoding="utf-8")
    (tmp_path / "AI_POLICY.md").write_text("ai-contributions: disclose\n\nWe never accept AI slop.\n", encoding="utf-8")
    got = policy.read(tmp_path)
    assert (got["stance"], got["file"], got["source"]) == ("disclose", "AI_POLICY.md", "marker")
    assert got["files"] == ["AI_POLICY.md", "CONTRIBUTING.md"]


def test_no_policy_file_or_none_about_ai_is_unstated_and_allowed(tmp_path):
    assert policy.read(tmp_path)["stance"] == "unstated"
    (tmp_path / "CONTRIBUTING.md").write_text("Run make test first.\n", encoding="utf-8")
    got = policy.read(tmp_path)
    assert got["stance"] == "unstated" and got["files"] == ["CONTRIBUTING.md"] and policy.may_open_pr("unstated")


def test_conditional_needs_a_person_and_the_disclosure_line_always_discloses():
    assert not policy.may_open_pr("conditional") and policy.may_open_pr("conditional", human_confirmed=True)
    assert "AI coding agent (Hermes Agent)" in policy.disclosure("disclose", "Hermes Agent")
    assert "A person confirmed" in policy.disclosure("conditional")
    assert policy.disclosure("allowed", ai_used=False) == "AI use: none (declared by the author)."


def test_a_reader_function_reads_the_policy_from_somewhere_else_than_the_disk():
    files = {".github/CONTRIBUTING.md": "AI-made pull requests are not accepted."}
    got = policy.read(get=files.get)
    assert got["stance"] == "banned" and got["file"] == ".github/CONTRIBUTING.md"
