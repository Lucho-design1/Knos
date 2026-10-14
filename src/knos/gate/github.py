"""The few GitHub calls Gate makes, through one `send(method, path, body) -> json` so tests replace the network.

    upsert_comment     ONE comment per pull request: the one carrying MARKER and written by `me` is edited in place;
                       a second one Gate finds (an earlier run's duplicate) is deleted
    upsert_check       ONE check run named CHECK_NAME per head commit (App mode only: a GitHub App can write checks,
                       an Action's own job already is the check)
    label / unlabel / close
    dispatch           workflow_dispatch of the gate workflow (App mode)"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import CHECK_NAME, MARKER

API = "https://api.github.com"


def http(token: str | None, base: str = API):
    def send(method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(f"{base}/{path.lstrip('/')}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "knos-gate",
                                              "X-GitHub-Api-Version": "2022-11-28",
                                              **({"Authorization": f"Bearer {token}"} if token else {}),
                                              **({} if body is None else {"Content-Type": "application/json"})})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - api.github.com
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise OSError(f"GitHub said {e.code} to {method} {path}") from None
        return json.loads(raw) if raw.strip() else None
    return send


class Client:
    def __init__(self, repo: str, send=None, token: str | None = None):
        self.repo = repo
        self.send = send or http(token if token is not None else os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))

    def _pages(self, path: str, limit: int = 10) -> list:
        out: list = []
        sep = "&" if "?" in path else "?"
        for page in range(1, limit + 1):
            got = self.send("GET", f"{path}{sep}per_page=100&page={page}") or []
            out += got
            if len(got) < 100:
                break
        return out

    def upsert_comment(self, pr: int, body: str, me: str | None = None) -> dict:
        """Edit Gate's comment on the pull request, or create it. `me`: the login Gate posts as (github-actions[bot]
        for an Action, <app-slug>[bot] for the App); a comment with MARKER by anyone else is not Gate's."""
        mine = [c for c in self._pages(f"repos/{self.repo}/issues/{pr}/comments")
                if MARKER in (c.get("body") or "") and (me is None or (c.get("user") or {}).get("login") == me)]
        if not mine:
            return self.send("POST", f"repos/{self.repo}/issues/{pr}/comments", {"body": body}) or {}
        keep, extra = mine[0], mine[1:]
        got = self.send("PATCH", f"repos/{self.repo}/issues/comments/{keep['id']}", {"body": body}) or keep
        for c in extra:
            self.send("DELETE", f"repos/{self.repo}/issues/comments/{c['id']}")
        return got

    def upsert_check(self, head: str, *, status: str, conclusion: str | None = None, title: str = "", summary: str = "",
                     details_url: str = "", external_id: str = "") -> dict:
        runs = (self.send("GET", f"repos/{self.repo}/commits/{head}/check-runs?check_name={urllib.parse.quote(CHECK_NAME)}&filter=latest") or {}).get("check_runs", [])
        body: dict = {"name": CHECK_NAME, "head_sha": head, "status": status}
        if conclusion:
            body["conclusion"] = conclusion
        if title or summary:
            body["output"] = {"title": title[:250], "summary": summary[:60000]}
        if details_url:
            body["details_url"] = details_url
        if external_id:
            body["external_id"] = external_id
        if runs:
            body.pop("head_sha")
            return self.send("PATCH", f"repos/{self.repo}/check-runs/{runs[0]['id']}", body) or {}
        return self.send("POST", f"repos/{self.repo}/check-runs", body) or {}

    def label(self, pr: int, labels: list[str]) -> None:
        if labels:
            self.send("POST", f"repos/{self.repo}/issues/{pr}/labels", {"labels": labels})

    def unlabel(self, pr: int, labels: list[str]) -> None:
        for name in labels:
            try:
                self.send("DELETE", f"repos/{self.repo}/issues/{pr}/labels/{urllib.parse.quote(name)}")
            except OSError:
                pass        # not there

    def close(self, pr: int) -> None:
        self.send("PATCH", f"repos/{self.repo}/pulls/{pr}", {"state": "closed"})

    def dispatch(self, workflow: str, ref: str, inputs: dict) -> None:
        self.send("POST", f"repos/{self.repo}/actions/workflows/{workflow}/dispatches", {"ref": ref, "inputs": inputs})

    def apply(self, pr: int, act: dict) -> None:
        self.unlabel(pr, act.get("remove_labels") or [])
        self.label(pr, act.get("add_labels") or [])
        if act.get("close"):
            self.close(pr)
