"""The data an outcome is measured on: read, parsed into rows, cut to the window, and hashed.

Two sources:
    file   a CSV, JSON or JSONL file in the buyer's repository, at the commit measured or at `data.ref` (a branch or a
           tag the workflow fetches). The data's name in the result and in the pay audience is that commit.
    http   a JSON endpoint. Its token is read from the environment variable the spec NAMES (`data.token_secret`), which
           the workflow fills from the buyer's GitHub secret of that name; the token is never written anywhere. The
           data's name is the first 40 hex digits of the sha256 of the bytes served.

`history_hash` is the hash of the rows dated before the window opens. It is written in the lock at funding and
compared at measurement: rows from before the window that were edited, added or removed afterwards are tampering.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metric import row_values


class DataError(ValueError):
    pass


def parse(raw: bytes, fmt: str, items_key: str | None = None) -> list[dict]:
    text = raw.decode("utf-8-sig")
    if fmt == "csv":
        return [row_values(dict(r)) for r in csv.DictReader(io.StringIO(text))]
    if fmt == "jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    doc = json.loads(text)
    if items_key:
        doc = doc.get(items_key) if isinstance(doc, dict) else None
    if not isinstance(doc, list) or not all(isinstance(r, dict) for r in doc):
        raise DataError("the JSON data must be a list of objects" + (f" under `{items_key}`" if items_key else ""))
    return doc


def when(v: Any) -> int:
    """A row's time as unix seconds: an integer, or ISO 8601 UTC text (Z or +00:00)."""
    if isinstance(v, bool) or v is None:
        raise DataError(f"not a time: {v!r}")
    if isinstance(v, (int, float)):
        return int(v)
    t = str(v).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        raise DataError(f"not a time: {v!r}") from None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def git_read(repo: Path, ref: str | None, path: str) -> tuple[bytes, str]:
    """(the file's bytes at `ref` (default HEAD), that commit's sha)."""
    at = ref or "HEAD"
    for name in ([at] if ref is None else [f"origin/{ref}", ref]):     # a fetched branch is origin/<ref> in a checkout
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"], capture_output=True, text=True, check=False)  # noqa: S603, S607
        if not sha.returncode:
            break
    else:
        raise DataError(f"git cannot find {at} in {repo}: fetch it first (git fetch origin {at})")
    raw = subprocess.run(["git", "-C", str(repo), "show", f"{sha.stdout.strip()}:{path}"], capture_output=True, check=False)  # noqa: S603, S607
    if raw.returncode:
        raise DataError(f"{path} is not in {at}: {raw.stderr.decode(errors='replace').strip()[-200:]}")
    return raw.stdout, sha.stdout.strip()


def http_read(url: str, token_env: str | None, env: Mapping[str, str] | None = None, opener=None) -> bytes:
    env = os.environ if env is None else env
    headers = {"Accept": "application/json", "User-Agent": "knos-outcome"}
    if token_env:
        token = env.get(token_env, "")
        if not token:
            raise DataError(f"the environment has no {token_env}: the workflow sets it from the buyer's secret passed as data_token")
        headers["Authorization"] = f"Bearer {token}"
    if not url.startswith("https://"):
        raise DataError("an http data source must be https")
    req = urllib.request.Request(url, headers=headers)
    # no redirect is followed: urllib would carry the token to wherever the endpoint points
    with (opener or urllib.request.build_opener(_NoRedirect).open)(req, timeout=30) as r:     # noqa: S310
        return r.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        raise DataError(f"the data endpoint answered with a redirect ({code}); the token is sent to the named URL only")


def read(spec: dict, repo: Path | None = None, *, raw: bytes | None = None, commit: str | None = None, env: dict | None = None,
         opener=None) -> tuple[list[dict], str, str]:
    """(rows, the data's 40-hex name, sha256 of the bytes). `raw` and `commit` stand in for the read (tests, or a
    file the caller already fetched)."""
    d = spec["data"]
    if raw is None:
        if d["source"] == "file":
            if repo is None:
                p = Path(d["path"])
                raw, commit = p.read_bytes(), None
            else:
                raw, commit = git_read(repo, d.get("ref"), d["path"])
        else:
            raw = http_read(d["url"], d.get("token_secret"), env, opener)
    digest = hashlib.sha256(raw).hexdigest()
    name = commit if commit and len(commit) == 40 else digest[:40]
    return parse(raw, d["format"], d.get("items_key")), name, digest


def rows_hash(rows: list[dict]) -> str:
    canon = sorted(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str) for r in rows)
    return hashlib.sha256("\n".join(canon).encode()).hexdigest()


def history_hash(spec: dict, rows: list[dict]) -> str:
    """sha256 of the rows dated before the window opens (canonical, order-free)."""
    from .spec import utc
    start, tf = utc(spec["window"]["start"]), spec["data"]["time_field"]
    return rows_hash([r for r in rows if when(r.get(tf)) < start])


def in_window(spec: dict, rows: list[dict]) -> list[dict]:
    from .spec import utc
    start, end, tf = utc(spec["window"]["start"]), utc(spec["window"]["end"]), spec["data"]["time_field"]
    out = []
    for r in rows:
        if tf not in r:
            raise DataError(f"a row has no `{tf}` (data.time_field)")
        if start <= when(r[tf]) < end:
            out.append(r)
    return out


def duplicates(spec: dict, rows: list[dict]) -> list[str]:
    idf = spec["data"]["id_field"]
    seen: set[str] = set()
    dup: list[str] = []
    for r in rows:
        if idf not in r:
            raise DataError(f"a row has no `{idf}` (data.id_field)")
        k = str(r[idf])
        if k in seen:
            dup.append(k)
        seen.add(k)
    return dup
