"""Reading the AIDev dataset (hao-li/AIDev on Hugging Face) into the audit's per-pull-request rows.

Only column subsets are read, through DuckDB, and the one large table (pr_commit_details, ~1.3 GB) is streamed in
record batches with a memory cap, so the audit runs in well under 2 GB of RAM. The dataset is never copied into the
repository: `--data` points at a local download (see docs/reference/BENCH.md for the exact files and revision).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import rules

REVISION = "bc7996907b404359f581c43d5160afe6ed599a14"     # the v4 tag of hao-li/AIDev (AIDev-2.7M, cutoff Nov 2025)
TABLES = ("pull_request.parquet", "pr_commit_details.parquet")


def _con(memory: str = "1200MB"):
    import duckdb

    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory}'")
    con.execute("SET threads=2")
    return con


def pull_requests(data: Path) -> dict[int, dict]:
    """Every agent pull request of AIDev-pop: id -> {agent, merged, repo, number, claims}. The body is read once,
    here, by Knos's own claim reader, and not kept."""
    con = _con()
    cur = con.execute(f"SELECT id, agent, merged_at IS NOT NULL AS merged, repo_url, number, html_url, body "
                      f"FROM '{data / 'pull_request.parquet'}'")
    out: dict[int, dict] = {}
    while batch := cur.fetchmany(5000):
        for pid, agent, merged, repo_url, number, html_url, body in batch:
            repo = str(repo_url or "").split("api.github.com/repos/", 1)[-1]
            out[int(pid)] = {"id": int(pid), "agent": str(agent), "merged": bool(merged), "repo": repo,
                             "number": int(number), "claims": rules.read_claims(body)}
    return out


# the files whose patch the rules read (a superset of rules.is_test / rules.is_ci, on the lower-cased path)
_READ_PATCH = ("(test|spec|conftest|e2e|it\\.(java|kt|kts|scala|groovy|cs|swift)$|\\.github/workflows|ci\\.ya?ml|\\.circleci|"
               "jenkinsfile|pipelines|buildkite)")


def file_signals(data: Path, log=print, checkpoint: Path | None = None) -> dict[int, list[dict]]:
    """pr_id -> [rules.file_signals(...) of each changed file of each commit]. Two passes over pr_commit_details: the
    patch column (nearly all of the table's bytes) is read only for the files the rules read, test and CI files.
    With `checkpoint`, pass 1 appends each file's signals there as it goes and a restarted run continues after the
    last row it holds (rows are read in file order)."""
    con = _con()
    src = f"read_parquet('{data / 'pr_commit_details.parquet'}', file_row_number=true)"
    read: dict[int, dict] = {}
    done = checkpoint is not None and checkpoint.with_suffix(".done").exists()
    if checkpoint is not None and checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            try:
                n, sig = json.loads(line)
            except ValueError:
                break                                   # a line cut by a kill: everything after it is read again
            read[int(n)] = sig
    if not done:
        after = max(read, default=-1)
        log(f"pass 1 from row {after + 1} ({len(read)} kept)")
        sink = checkpoint.open("a") if checkpoint is not None else None
        cur = con.execute(f"SELECT file_row_number, filename, status, patch FROM {src} WHERE file_row_number > {after} "
                          f"AND regexp_matches(lower(filename), '{_READ_PATCH}')").fetch_record_batch(5000)
        for batch in cur:
            d = batch.to_pydict()
            lines = []
            for n, fn, st, patch in zip(d["file_row_number"], d["filename"], d["status"], d["patch"]):
                read[int(n)] = sig = rules.file_signals(fn, st, patch)
                lines.append(json.dumps([int(n), sig]) + "\n")
            if sink:
                sink.write("".join(lines))
                sink.flush()
            if len(read) // 50000 != (len(read) - len(lines)) // 50000:
                log(f"patches read: {len(read)}")
        if sink:
            sink.close()
            checkpoint.with_suffix(".done").write_text("")
    log(f"patches read: {len(read)} (pass 1 done)")
    out: dict[int, list[dict]] = {}
    seen = 0
    cur = con.execute(f"SELECT file_row_number, pr_id, filename, status FROM {src}").fetch_record_batch(50000)
    for batch in cur:
        d = batch.to_pydict()
        for n, pid, fn, st in zip(d["file_row_number"], d["pr_id"], d["filename"], d["status"]):
            if pid is None or not fn:
                continue
            sig = read.get(int(n)) or rules.file_signals(fn, st, None)
            out.setdefault(int(pid), []).append(sig)
        seen += len(d["pr_id"])
    log(f"file rows: {seen} (pass 2 done)")
    return out


V3_REVISION = "3ca0045773097b138b064550dfd6e72229f40bee"   # the v3 tag: the last version with related_issue


def issue_links(v3: Path) -> list[list[int]]:
    """[pr_id, issue_id] for every agent pull request whose description links an issue (AIDev v3 related_issue; v4
    dropped that table, and v3's pull requests are in v4 under the same ids)."""
    con = _con("400MB")
    return [[int(p), int(i)] for p, i in con.execute(
        f"SELECT pr_id, CAST(issue_id AS BIGINT) FROM '{v3 / 'related_issue.parquet'}' WHERE issue_id IS NOT NULL "
        f"ORDER BY 1, 2").fetchall()]


def build_rows(data: Path, cache: Path | None = None) -> list[dict]:
    """The audit's rows from a local AIDev download. With `cache`, the rows are kept there as JSON lines and read
    back on a second call (the CI reading is joined later, by __main__)."""
    if cache and cache.exists():
        return [json.loads(x) for x in cache.read_text().splitlines() if x.strip()]
    kept = cache.with_name("prs.json") if cache else None
    if kept and kept.exists():
        prs = {int(k): v for k, v in json.loads(kept.read_text()).items()}
    else:
        prs = pull_requests(data)
        if kept:
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_text(json.dumps(prs))
    print(f"pull requests read: {len(prs)}", flush=True)
    files = file_signals(data, log=lambda s: print(s, flush=True), checkpoint=cache.with_name("patch_signals.jsonl") if cache else None)
    rows = []
    for pid, pr in sorted(prs.items()):
        f = files.get(pid)
        rows.append({**pr, "has_files": bool(f), "diff": rules.pr_signals(f) if f else None, "ci": None})
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        os.replace(tmp, cache)
    return rows
