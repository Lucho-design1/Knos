"""The GitHub App (not registered): webhook signatures, the App's JWT, and one check + one comment from its events."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import zipfile
from pathlib import Path

import pytest

from knos.gate import CHECK_NAME, MARKER, app

ROOT = Path(__file__).resolve().parents[1]
HEAD = "e" * 40


def test_signature():
    body, secret = b'{"a":1}', b"s3"
    good = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    assert app.verify_signature(secret, body, good)
    assert not app.verify_signature(secret, body + b" ", good)
    assert not app.verify_signature(b"other", body, good)
    assert not app.verify_signature(secret, body, None) and not app.verify_signature(secret, body, "sha1=00")


def test_app_jwt_is_rs256_and_verifies():
    crypto = pytest.importorskip("cryptography")  # noqa: F841
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
    tok = app.app_jwt("12345", pem, now=1_000_000)
    h, c, s = tok.split(".")
    pad = lambda x: base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))  # noqa: E731
    assert json.loads(pad(h)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(pad(c)) == {"iat": 999_940, "exp": 1_000_540, "iss": "12345"}
    key.public_key().verify(pad(s), f"{h}.{c}".encode(), padding.PKCS1v15(), hashes.SHA256())


def test_the_manifest_file_is_the_code_manifest():
    assert json.loads((ROOT / "github-app" / "app-manifest.json").read_text()) == app.MANIFEST
    perms = app.MANIFEST["default_permissions"]
    assert perms["contents"] == "read" and "administration" not in perms and "secrets" not in perms


class Hub:
    def __init__(self, gate_yml=True, head=HEAD):
        self.calls, self.comments, self.runs, self.gate_yml, self.head = [], [], [], gate_yml, head

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("repos/o/r/contents/.knos/gate.yml"):
            if not self.gate_yml:
                raise OSError("404")
            return {"name": "gate.yml"}
        if "/check-runs" in path and method == "GET":
            return {"check_runs": self.runs}
        if path.endswith("/check-runs") and method == "POST":
            self.runs.append({"id": 1, **body})
            return self.runs[-1]
        if "/check-runs/" in path and method == "PATCH":
            self.runs[0].update(body)
            return self.runs[0]
        if path.endswith("/artifacts"):
            return {"artifacts": [{"name": "knos-gate", "archive_download_url": "https://api.github.com/x/zip"}]}
        if path == "repos/o/r/pulls/4":
            return {"head": {"sha": self.head}}
        if "/comments" in path and method == "GET":
            return self.comments
        if path.endswith("/comments") and method == "POST":
            self.comments.append({"id": 9, "body": body["body"], "user": {"login": "knos-gate[bot]"}})
            return self.comments[-1]
        if "/issues/comments/" in path and method == "PATCH":
            self.comments[0]["body"] = body["body"]
            return self.comments[0]
        return None


def pr_event(action="opened"):
    return {"action": action, "repository": {"full_name": "o/r", "default_branch": "main"},
            "pull_request": {"number": 4, "draft": False, "head": {"sha": HEAD}, "base": {"ref": "main", "sha": "b" * 40}}}


def artifact(passed):
    v = {"repo": "o/r", "pr": 4, "head": HEAD, "passed": passed, "rule": "" if passed else "gate.test_edited", "reasons": [] if passed else ["test_edited"],
         "mode": "hidden", "findings": [], "hidden": None, "public": None, "library": "local",
         "actions": {"close": not passed, "add_labels": [], "remove_labels": []}}
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("verdict.json", json.dumps(v))
        z.writestr("comment.md", f"{MARKER}\nverdict {'passed' if passed else 'refused'}")
    return raw.getvalue()


def test_a_pull_request_starts_one_check_and_dispatches_the_workflow():
    hub = Hub()
    done = app.handle("pull_request", pr_event(), hub)
    assert len(hub.runs) == 1 and hub.runs[0]["status"] == "in_progress" and hub.runs[0]["name"] == CHECK_NAME
    disp = [c for c in hub.calls if c[1].endswith("/dispatches")]
    assert disp == [("POST", "repos/o/r/actions/workflows/knos-gate.yml/dispatches", {"ref": "main", "inputs": {"pr": "4", "head": HEAD}})]
    assert any("dispatched" in d for d in done)


def test_no_config_no_check():
    hub = Hub(gate_yml=False)
    assert "not set up" in app.handle("pull_request", pr_event(), hub)[0] and hub.runs == []


def test_the_finished_run_completes_the_same_check_and_one_comment():
    hub = Hub()
    app.handle("pull_request", pr_event(), hub)
    wr = {"action": "completed", "repository": {"full_name": "o/r"},
          "workflow_run": {"id": 77, "path": ".github/workflows/knos-gate.yml", "event": "workflow_dispatch", "html_url": "https://github.com/o/r/actions/runs/77"}}
    app.handle("workflow_run", wr, hub, download=lambda url, tok: artifact(False))
    app.handle("workflow_run", wr, hub, download=lambda url, tok: artifact(True))
    assert len(hub.runs) == 1 and hub.runs[0]["conclusion"] == "success"
    assert len(hub.comments) == 1 and "passed" in hub.comments[0]["body"]
    assert ("PATCH", "repos/o/r/pulls/4", {"state": "closed"}) in hub.calls        # the refused run's on_fail: close


def test_a_verdict_for_an_older_head_does_not_decide():
    hub = Hub(head="f" * 40)
    wr = {"action": "completed", "repository": {"full_name": "o/r"},
          "workflow_run": {"id": 77, "path": ".github/workflows/knos-gate.yml", "event": "workflow_dispatch"}}
    assert "superseded" in app.handle("workflow_run", wr, hub, download=lambda u, t: artifact(True))[0]
    assert hub.comments == [] and hub.runs[0]["conclusion"] == "neutral"


def test_another_workflow_or_event_is_ignored():
    hub = Hub()
    wr = {"action": "completed", "repository": {"full_name": "o/r"},
          "workflow_run": {"id": 1, "path": ".github/workflows/ci.yml", "event": "pull_request"}}
    assert "not the gate workflow" in app.handle("workflow_run", wr, hub)[0]
    assert app.handle("issues", {"action": "opened", "repository": {"full_name": "o/r"}}, hub)[0].startswith("ignored")


# ---- review fix: minor 40 (a run with no verdict does not leave the check in progress) ----

def test_a_run_without_a_verdict_completes_the_check_as_failure():
    hub = Hub()
    app.handle("pull_request", pr_event(), hub)
    wr = {"action": "completed", "repository": {"full_name": "o/r"},
          "workflow_run": {"id": 78, "path": ".github/workflows/knos-gate.yml", "event": "workflow_dispatch",
                           "display_title": f"Knos Gate #4 {HEAD}", "html_url": "https://github.com/o/r/actions/runs/78"}}
    got = app.handle("workflow_run", wr, hub, download=lambda u, t: b"not a zip")
    assert "completed as failure" in got[0] and hub.runs[0]["status"] == "completed" and hub.runs[0]["conclusion"] == "failure"
    assert "run-name: \"Knos Gate #${{ inputs.pr }} ${{ inputs.head }}\"" in (ROOT / "github-app" / "knos-gate.yml").read_text()
