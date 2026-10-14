"""Exactly one comment and one check per pull request, each edited in place; the words of both."""
from __future__ import annotations

from knos.gate import CHECK_NAME, MARKER, report
from knos.gate import verdict as V
from knos.gate.github import Client


class Fake:
    def __init__(self, comments=(), runs=()):
        self.comments = [dict(c) for c in comments]
        self.runs = [dict(r) for r in runs]
        self.calls = []
        self.next = 1000

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and "/comments" in path:
            return self.comments if "page=1" in path else []
        if method == "POST" and path.endswith("/comments"):
            self.next += 1
            c = {"id": self.next, "body": body["body"], "user": {"login": "github-actions[bot]"}}
            self.comments.append(c)
            return c
        if method == "PATCH" and "/issues/comments/" in path:
            cid = int(path.rsplit("/", 1)[1])
            for c in self.comments:
                if c["id"] == cid:
                    c["body"] = body["body"]
            return {"id": cid}
        if method == "DELETE" and "/issues/comments/" in path:
            cid = int(path.rsplit("/", 1)[1])
            self.comments = [c for c in self.comments if c["id"] != cid]
            return None
        if method == "GET" and "/check-runs" in path:
            return {"check_runs": self.runs}
        if method == "POST" and path.endswith("/check-runs"):
            self.runs.append({"id": 5, **body})
            return self.runs[-1]
        if method == "PATCH" and "/check-runs/" in path:
            self.runs[0].update(body)
            return self.runs[0]
        return None


def verdict(passed=True):
    return {"type": "knos.gate-verdict", "repo": "o/r", "pr": 3, "head": "c" * 40, "base": "b" * 40, "passed": passed,
            "rule": "" if passed else "gate.hidden_tests_failed", "reasons": [] if passed else ["hidden tests: 1 of 2 passed, 1 failed"],
            "mode": "hidden", "spec_hash": "a" * 64, "hidden": {"total": 2, "passed": 2 if passed else 1, "failed": 0 if passed else 1, "errors": 0},
            "public": None, "findings": [], "library": "local", "run_url": "https://github.com/o/r/actions/runs/1"}


def test_the_comment_is_created_once_then_edited_in_place():
    gh = Fake()
    c = Client("o/r", send=gh)
    c.upsert_comment(3, report.comment(verdict(False)))
    c.upsert_comment(3, report.comment(verdict(True)))
    c.upsert_comment(3, report.comment(verdict(True)))
    assert len(gh.comments) == 1 and "passed" in gh.comments[0]["body"] and MARKER in gh.comments[0]["body"]
    assert sum(1 for m, p, _ in gh.calls if m == "POST") == 1


def test_a_duplicate_comment_is_removed_and_others_are_left_alone():
    gh = Fake(comments=[{"id": 1, "body": MARKER + " old", "user": {"login": "github-actions[bot]"}},
                        {"id": 2, "body": MARKER + " dup", "user": {"login": "github-actions[bot]"}},
                        {"id": 3, "body": MARKER + " someone quoting it", "user": {"login": "mallory"}}])
    Client("o/r", send=gh).upsert_comment(3, "new " + MARKER, me="github-actions[bot]")
    assert [c["id"] for c in gh.comments] == [1, 3] and gh.comments[0]["body"] == "new " + MARKER


def test_one_check_run_per_head_edited_in_place():
    gh = Fake()
    c = Client("o/r", send=gh)
    c.upsert_check("c" * 40, status="in_progress", title="running")
    c.upsert_check("c" * 40, status="completed", conclusion="success", title="done", summary="ok")
    assert len(gh.runs) == 1 and gh.runs[0]["conclusion"] == "success" and gh.runs[0]["name"] == CHECK_NAME


def test_actions_follow_on_fail():
    cfg = {"on_fail": "label", "label": "knos-gate-failed", "pass_label": "knos-verified"}
    assert V.actions(verdict(False), cfg) == {"close": False, "add_labels": ["knos-gate-failed"], "remove_labels": ["knos-verified"]}
    assert V.actions(verdict(False), {**cfg, "on_fail": "close"})["close"] is True
    assert V.actions(verdict(False), {**cfg, "on_fail": "comment"})["add_labels"] == []
    gh = Fake()
    Client("o/r", send=gh).apply(3, {"close": True, "add_labels": ["x"], "remove_labels": ["y"]})
    assert [(m, p) for m, p, _ in gh.calls] == [("DELETE", "repos/o/r/issues/3/labels/y"), ("POST", "repos/o/r/issues/3/labels"),
                                                 ("PATCH", "repos/o/r/pulls/3")]


def test_words():
    assert report.title(verdict(True)) == "Knos Gate: passed"
    assert report.title(verdict(False)) == "Knos Gate: refused (gate.hidden_tests_failed)"
    text = report.comment(verdict(False))
    assert "re-run" in text and "turn on Knos Gate for your repo" in text and "1/2 passed" in text
    assert V.outside("CONTRIBUTOR") and V.outside(None) and not V.outside("OWNER")


def test_the_module_entry_point_returns_the_verdicts_exit_code(tmp_path):
    from knos.gate import cli
    assert cli.main(["validate", str(tmp_path)]) == 1          # no .knos/gate.yml: exit 1, as the Action's step needs
    (tmp_path / ".knos").mkdir()
    (tmp_path / ".knos" / "gate.yml").write_text("version: 1\npublic_tests:\n  command: pytest\n")
    assert cli.main(["validate", str(tmp_path)]) == 0
