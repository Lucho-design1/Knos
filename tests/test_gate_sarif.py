"""Gate's refused cheats in GitHub's own places: a SARIF 2.1.0 log for code scanning, check-run annotations (App mode),
`::error` workflow commands (Action mode), and the artifact attestation step of the Action (docs/reference/REFEREE.md)."""
from __future__ import annotations

import base64
import gzip
import io
import json
import zipfile
from pathlib import Path

from test_gate_e2e import GOOD, LAZY, judge, repo  # noqa: F401 - the fixture and the helpers of the end-to-end tests

from knos.gate import CHECK_NAME, MARKER, app, sarif
from knos.gate.github import Client

ROOT = Path(__file__).resolve().parents[1]
DIFF = """diff --git a/tests/test_public.py b/tests/test_public.py
index 1..2 100644
--- a/tests/test_public.py
+++ b/tests/test_public.py
@@ -1,4 +1,4 @@
 from slugs import slug

-def test_lower():
-    assert slug('ABC') == 'abc'
+def test_lower():
+    pass
diff --git a/data/words.txt b/data/words.txt
deleted file mode 100644
--- a/data/words.txt
+++ /dev/null
@@ -1 +0,0 @@
-synthetic
"""
V = {"repo": "o/r", "pr": 4, "head": "e" * 40, "passed": False,
     "findings": [{"rule": "gate.test_edited", "category": "test_edited", "path": "tests/test_public.py", "detail": "edits or deletes an existing test", "severity": "refuse"},
                  {"rule": "gate.data_tampering", "category": "data_tampering", "path": "data/words.txt", "detail": "changes data", "severity": "refuse"},
                  {"rule": "referee.advisory", "category": "advisory", "path": "src/x.py", "detail": "only a note", "severity": "warn"}]}


def test_the_first_changed_line_of_each_file_is_read_from_the_diff():
    assert sarif.first_lines(DIFF) == {"tests/test_public.py": 3}          # a removed-only file has none


def test_the_sarif_log_has_one_error_per_refused_finding_at_its_line_with_a_stable_fingerprint():
    log = sarif.sarif(V, DIFF, "0.3.31")
    assert log["version"] == "2.1.0" and log["$schema"].endswith("sarif-2.1.0.json")
    run = log["runs"][0]
    assert run["tool"]["driver"]["name"] == CHECK_NAME and run["automationDetails"]["id"] == "knos-gate/"
    res = run["results"]
    assert [r["ruleId"] for r in res] == ["gate.test_edited", "gate.data_tampering"]       # the advisory one is not an alert
    assert res[0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 3
    assert res[1]["locations"][0]["physicalLocation"]["region"]["startLine"] == 1
    assert all(r["level"] == "error" and run["tool"]["driver"]["rules"][r["ruleIndex"]]["id"] == r["ruleId"] for r in res)
    # the same cheat on a later push is the same alert: the fingerprint names the rule and the path, not the line or commit
    later = sarif.sarif({**V, "head": "f" * 40}, DIFF.replace("@@ -1,4 +1,4 @@", "@@ -1,4 +7,4 @@"))
    assert [r["partialFingerprints"] for r in later["runs"][0]["results"]] == [r["partialFingerprints"] for r in res]
    rules = {r["id"] for r in run["tool"]["driver"]["rules"]}
    assert "gate.workflow_edited" in rules and all(r["properties"]["security-severity"] for r in run["tool"]["driver"]["rules"])


def test_a_passing_verdict_uploads_an_empty_log_which_closes_earlier_alerts():
    log = sarif.sarif({**V, "passed": True, "findings": []})
    assert log["runs"][0]["results"] == [] and log["runs"][0]["properties"]["passed"] is True


def test_annotations_are_capped_at_fifty_and_read_back_from_the_log():
    many = {**V, "findings": [dict(V["findings"][0], path=f"tests/t{i}.py") for i in range(70)]}
    notes = sarif.annotations(many)
    assert len(notes) == sarif.MAX_ANNOTATIONS and notes[0] == {
        "path": "tests/t0.py", "start_line": 1, "end_line": 1, "annotation_level": "failure",
        "title": "Knos Gate: test_edited (gate.test_edited)", "message": "edits or deletes an existing test"}
    back = sarif.from_sarif(sarif.sarif(V, DIFF))
    assert [(a["path"], a["start_line"]) for a in back] == [("tests/test_public.py", 3), ("data/words.txt", 1)]


def test_workflow_commands_escape_what_would_end_the_command():
    line = sarif.workflow_commands([{"path": "a,b:c.py", "start_line": 2, "title": "T: x", "message": "50%\nnext"}])
    assert line == "::error file=a%2Cb%3Ac.py,line=2,title=T%3A x::50%25%0Anext\n"


def test_upload_sarif_posts_gzip_base64_of_the_log_at_the_head_and_ref():
    sent = []
    c = Client("o/r", send=lambda m, p, b=None: sent.append((m, p, b)) or {"id": "u1", "url": "x"})
    assert c.upload_sarif("e" * 40, "refs/pull/4/head", sarif.sarif(V, DIFF)) == {"id": "u1", "url": "x"}
    (m, p, b), = sent
    assert (m, p) == ("POST", "repos/o/r/code-scanning/sarifs") and b["commit_sha"] == "e" * 40 and b["ref"] == "refs/pull/4/head"
    assert json.loads(gzip.decompress(base64.b64decode(b["sarif"])))["runs"][0]["results"][0]["ruleId"] == "gate.test_edited"
    assert b["tool_name"] == CHECK_NAME


def test_more_than_fifty_annotations_go_out_fifty_a_request():
    sent = []

    def send(m, p, b=None):
        sent.append((m, p, b))
        return {"check_runs": []} if m == "GET" else {"id": 5}
    notes = [{"path": f"f{i}", "start_line": 1, "end_line": 1, "annotation_level": "failure", "message": "m"} for i in range(120)]
    Client("o/r", send=send).upsert_check("e" * 40, status="completed", conclusion="failure", title="t", summary="s", annotations=notes)
    batches = [len(b["output"]["annotations"]) for m, _, b in sent if m in ("POST", "PATCH")]
    assert batches == [50, 50, 20] and sent[1][1] == "repos/o/r/check-runs" and sent[2][1] == "repos/o/r/check-runs/5"


def test_gate_run_writes_the_log_and_the_annotations_beside_the_verdict(repo):  # noqa: F811
    got, out = judge(repo, "edit-tests-sarif", {"src/slugs.py": LAZY, "tests/test_public.py": "def test_lower():\n    pass\n"})
    log = json.loads((out / "knos-gate.sarif").read_text())
    assert got["sarif"] == log and log["runs"][0]["results"]
    assert {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in log["runs"][0]["results"]} >= {"tests/test_public.py"}
    assert json.loads((out / "annotations.json").read_text())[0]["annotation_level"] == "failure"
    good, out2 = judge(repo, "good-sarif", {"src/slugs.py": GOOD})
    assert good["verdict"]["passed"] and json.loads((out2 / "knos-gate.sarif").read_text())["runs"][0]["results"] == []


def test_post_uploads_the_log_only_when_asked(repo):  # noqa: F811
    from knos.gate import run as gate_run
    got, _ = judge(repo, "edit-tests-post", {"src/slugs.py": LAZY, "tests/test_public.py": "def test_lower():\n    pass\n"})
    calls = []
    c = Client("owner/demo", send=lambda m, p, b=None: calls.append((m, p)) or ([] if m == "GET" else {"id": 1}))
    assert gate_run.post(got, "owner/demo", 7, client=c) is None
    assert not any("code-scanning" in p for _, p in calls)
    assert gate_run.post(got, "owner/demo", 7, client=c, code_scanning=True) == {"id": 1}
    assert ("POST", "repos/owner/demo/code-scanning/sarifs") in calls


def test_the_app_annotates_its_check_and_uploads_the_log_from_the_artifact():
    calls, runs = [], []

    def hub(m, p, b=None):
        calls.append((m, p, b))
        if "/check-runs" in p and m == "GET":
            return {"check_runs": runs}
        if p.endswith("/check-runs") and m == "POST":
            runs.append({"id": 1, **b})
            return runs[-1]
        if p.endswith("/artifacts"):
            return {"artifacts": [{"name": "knos-gate", "archive_download_url": "https://api.github.com/x/zip"}]}
        if p == "repos/o/r/pulls/4":
            return {"head": {"sha": "e" * 40}}
        if "/comments" in p and m == "GET":
            return []
        return {"id": 9}
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("verdict.json", json.dumps({**V, "rule": "gate.test_edited", "reasons": ["x"], "mode": "hidden", "hidden": None,
                                               "public": None, "library": "local", "actions": {}}))
        z.writestr("comment.md", f"{MARKER}\nrefused")
        z.writestr("knos-gate.sarif", json.dumps(sarif.sarif(V, DIFF)))
    wr = {"action": "completed", "repository": {"full_name": "o/r"},
          "workflow_run": {"id": 77, "path": ".github/workflows/knos-gate.yml", "event": "workflow_dispatch"}}
    done = app.handle("workflow_run", wr, hub, download=lambda u, t: raw.getvalue())
    assert [a["path"] for a in runs[0]["output"]["annotations"]] == ["tests/test_public.py", "data/words.txt"]
    assert "code scanning: findings uploaded" in done
    assert app.MANIFEST["default_permissions"]["security_events"] == "write"


def test_the_action_offers_code_scanning_and_a_receipt_attestation_off_by_default():
    text = (ROOT / "actions" / "gate" / "action.yml").read_text()
    assert "code-scanning:" in text and 'post+=(--code-scanning)' in text and "--annotate" in text
    assert "uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in text and "steps.gate.outputs.receipt" in text
    assert text.count('default: "false"') >= 2


def test_a_ruleset_makes_the_gate_check_required_once():
    from knos.gate.github import RULESET, ruleset
    body = ruleset(4242)
    assert body["rules"] == [{"type": "required_status_checks", "parameters": {
        "required_status_checks": [{"context": CHECK_NAME, "integration_id": 4242}], "strict_required_status_checks_policy": False}}]
    assert body["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"] and body["enforcement"] == "active"
    sent = []
    assert Client("o/r", send=lambda m, p, b=None: sent.append(m)).require()["sent"] is None and sent == []     # nothing without apply
    have = []

    def send(m, p, b=None):
        sent.append((m, p))
        if m == "GET":
            return have
        have.append({"id": 3, "name": RULESET})
        return {"id": 3}
    c = Client("o/r", send=send)
    c.require(apply=True)
    c.require(apply=True)
    assert [x for x in sent if x[0] != "GET"] == [("POST", "repos/o/r/rulesets"), ("PUT", "repos/o/r/rulesets/3")]
