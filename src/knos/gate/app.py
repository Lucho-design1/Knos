"""The Knos Gate GitHub App: webhooks in, ONE check run and ONE comment out. github-app/server.py serves it.

NOT REGISTERED. Registering a GitHub App is a founder step (docs/reference/REFEREE.md, "Register the App"):
github-app/app-manifest.json is the manifest, and this code runs once its id, private key and webhook secret exist.

    pull_request (opened, reopened, synchronize, ready_for_review)
        the base has .knos/gate.yml: the check "Knos Gate" goes to in_progress and the repository's gate workflow
        (.github/workflows/knos-gate.yml, the same actions/gate with `report: app`) is dispatched for that pull request.
        A workflow_dispatch run belongs to the default branch, so it adds no check of its own to the pull request:
        the App's check stays the only one.
    workflow_run (completed) of that workflow
        the run's artifact `knos-gate` holds verdict.json, comment.md and the receipt; the App holds the verdict to
        the check's own head commit, then edits its check run and its comment in place and applies the labels
        (or closes, with on_fail: close or a failed bounty claim)
    check_run (rerequested)
        dispatches the workflow again

The workflow file is read from the default branch (a dispatch runs the default branch's copy), so a pull request
cannot change what judges it. The App's own permissions: checks write, pull requests write, issues write, actions
write (dispatch) and read (artifacts), contents read, metadata read, security events write (the cheat findings as
code-scanning alerts, knos.gate.sarif). Nothing else."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import time
import urllib.request
import zipfile

from . import CHECK_NAME, report
from .github import Client

WORKFLOW = "knos-gate.yml"
ARTIFACT = "knos-gate"
PR_ACTIONS = ("opened", "reopened", "synchronize", "ready_for_review")

MANIFEST = {
    "name": "Knos Gate",
    "url": "https://github.com/drexthealpha/Knos/blob/main/docs/reference/REFEREE.md",
    "description": "Runs a maintainer's sealed hidden tests and the Knos cheat checks on every outside pull request. One check, one comment, a signed receipt.",
    "hook_attributes": {"url": "https://REPLACE-WITH-YOUR-HOST/webhook", "active": True},
    "redirect_url": "https://REPLACE-WITH-YOUR-HOST/registered",
    "public": True,
    "default_permissions": {"checks": "write", "pull_requests": "write", "issues": "write", "actions": "write",
                            "contents": "read", "metadata": "read", "security_events": "write"},
    "default_events": ["pull_request", "workflow_run", "check_run"],
}


def verify_signature(secret: bytes, body: bytes, header: str | None) -> bool:
    """GitHub's X-Hub-Signature-256: sha256=<hex HMAC of the body under the webhook secret>."""
    if not header or not header.startswith("sha256="):
        return False
    want = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, header[7:])


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def app_jwt(app_id: str, private_key_pem: bytes, now: int | None = None) -> str:
    """The App's JWT (RS256, 9 minutes, issued 60 s in the past as GitHub advises). Needs `cryptography`
    (github-app/requirements.txt)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    t = int(time.time() if now is None else now)
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64(json.dumps({"iat": t - 60, "exp": t + 540, "iss": str(app_id)}, separators=(",", ":")).encode())
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("the App's private key is not an RSA key (GitHub gives one in PEM)")
    sig = key.sign(f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{claims}.{_b64(sig)}"


def installation_token(jwt: str, installation_id: int, send) -> str:
    got = send("POST", f"app/installations/{installation_id}/access_tokens", {}) if send else None
    return (got or {})["token"]


def _download(url: str, token: str) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                               "User-Agent": "knos-gate"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - api.github.com and its artifact storage
        return resp.read()


def read_artifact(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = set(z.namelist())
        out = {"verdict": json.loads(z.read("verdict.json")), "comment": z.read("comment.md").decode("utf-8")}
        if "receipt.json" in names:
            out["receipt"] = json.loads(z.read("receipt.json"))
        if "knos-gate.sarif" in names:
            out["sarif"] = json.loads(z.read("knos-gate.sarif"))
    return out


_TITLE = re.compile(r"#(\d+) ([0-9a-f]{40})\b")


def _no_verdict(gh: Client, wr: dict) -> list[str]:
    """The run ended without a readable verdict. Its title (`run-name` in github-app/knos-gate.yml) names the pull
    request and head, so the check the App started is completed as a failure instead of staying in progress."""
    m = _TITLE.search(str(wr.get("display_title") or wr.get("name") or ""))
    if not m:
        return ["the run left no verdict, and its title names no head commit"]
    gh.upsert_check(m.group(2), status="completed", conclusion="failure", title=f"{CHECK_NAME}: could not run",
                    summary="The gate workflow ended without a verdict. Open its run to see why, then re-run the check.",
                    details_url=wr.get("html_url", ""))
    return [f"no verdict: check on {m.group(2)[:7]} completed as failure"]


def handle(event: str, payload: dict, send, *, download=None, token: str = "", me: str = "knos-gate[bot]",
           code_scanning: bool = True) -> list[str]:
    """One webhook. `send` is a GitHub client's send (installation token). Returns what was done, for the log.
    `code_scanning`: also upload the run's SARIF log (the App's security_events permission); a refusal is logged, never fatal."""
    repo = (payload.get("repository") or {}).get("full_name", "")
    gh = Client(repo, send=send)
    done: list[str] = []
    if event == "pull_request" and payload.get("action") in PR_ACTIONS:
        pr = payload["pull_request"]
        if pr.get("draft"):
            return ["draft: not judged until ready"]
        base_ref = pr["base"]["ref"]
        try:
            send("GET", f"repos/{repo}/contents/.knos/gate.yml?ref={pr['base']['sha']}")
        except OSError:
            return ["no .knos/gate.yml on the base: Knos Gate is not set up here"]
        gh.upsert_check(pr["head"]["sha"], status="in_progress", title=f"{CHECK_NAME}: running",
                        summary="Running the sealed hidden tests and the cheat checks.", external_id=f"{repo}#{pr['number']}")
        default = (payload.get("repository") or {}).get("default_branch") or base_ref
        gh.dispatch(WORKFLOW, default, {"pr": str(pr["number"]), "head": pr["head"]["sha"]})
        done += [f"check in_progress on {pr['head']['sha'][:7]}", f"dispatched {WORKFLOW} for #{pr['number']}"]
    elif event == "check_run" and payload.get("action") == "rerequested":
        run = payload["check_run"]
        if run.get("name") != CHECK_NAME:
            return ["not our check"]
        prs = run.get("pull_requests") or []
        if not prs:
            return ["the check names no pull request"]
        default = (payload.get("repository") or {}).get("default_branch") or "main"
        gh.upsert_check(run["head_sha"], status="in_progress", title=f"{CHECK_NAME}: running again")
        gh.dispatch(WORKFLOW, default, {"pr": str(prs[0]["number"]), "head": run["head_sha"]})
        done.append(f"re-dispatched for #{prs[0]['number']}")
    elif event == "workflow_run" and payload.get("action") == "completed":
        wr = payload["workflow_run"]
        if not str(wr.get("path", "")).endswith(f"/{WORKFLOW}") or wr.get("event") != "workflow_dispatch":
            return ["not the gate workflow's dispatched run"]
        arts = (send("GET", f"repos/{repo}/actions/runs/{wr['id']}/artifacts") or {}).get("artifacts", [])
        art = next((a for a in arts if a.get("name") == ARTIFACT), None)
        got = None
        if art is not None:
            try:
                got = read_artifact((download or _download)(art["archive_download_url"], token))
            except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                got = None
        if got is None:
            return _no_verdict(gh, wr)
        v = got["verdict"]
        pull = send("GET", f"repos/{repo}/pulls/{v['pr']}") or {}
        if (pull.get("head") or {}).get("sha") != v.get("head"):
            gh.upsert_check(v["head"], status="completed", conclusion="neutral", title=f"{CHECK_NAME}: superseded",
                            summary="The pull request has a newer commit; that commit's run decides.")
            return ["verdict for an older head: marked superseded"]
        from . import sarif
        gh.upsert_check(v["head"], status="completed", conclusion="success" if v["passed"] else "failure",
                        title=report.title(v), summary=report.summary(v), details_url=wr.get("html_url", ""),
                        annotations=sarif.from_sarif(got["sarif"]) if got.get("sarif") else None)
        gh.upsert_comment(v["pr"], got["comment"], me=me)
        gh.apply(v["pr"], v.get("actions") or {})
        done += [f"check {'success' if v['passed'] else 'failure'} on {v['head'][:7]}", f"comment on #{v['pr']}"]
        if got.get("sarif") and code_scanning:
            try:                     # the App's `security_events: write`; a repository without code scanning answers 403/404
                gh.upload_sarif(v["head"], f"refs/pull/{v['pr']}/head", got["sarif"])
                done.append("code scanning: findings uploaded")
            except OSError as why:
                done.append(f"code scanning: not uploaded ({why})")
    else:
        done.append(f"ignored {event}/{payload.get('action')}")
    return done
