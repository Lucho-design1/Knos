"""Export a merged issue + pull request as a sealed task package, and check one.

A package is a folder:

    <task_id>/public/task.json     the manifest: source, licence, opt-in, statement, scope, judge, sealed hashes, the check
                                   that the task is real (fail before the fix, pass after), and the fee split
    <task_id>/public/statement.md  the issue as the solver sees it
    <task_id>/sealed/tests.tar     the hidden tests: the test files the merged fix added or changed (deterministic tar)
    <task_id>/sealed/reference.patch   the merged fix without its tests (for the buyer's own validation)
    <task_id>.key                  only with --encrypt: the key, written BESIDE the package folder, never inside it (never
                                   printed); hand the package to a buyer without it, and the key separately

The task id is derived from the spec hash: sha256 of the canonical manifest without the id and the hash, which commits to
the sealed files' sha256. Nothing in public/ reveals a hidden test's content or name.

Rules a package keeps (each refuses the export with its reason):
  - maintainer opt-in: .knos/taskpack.yml with `export: true` at the merge commit, or --opt-in given by the maintainer
    running the export (recorded as such in the manifest);
  - the fix must carry tests (nothing to seal otherwise) and change at least one non-test file;
  - the task must be real: at the base commit with the hidden tests added the judge FAILS, and at the merge it PASSES.
The licence is read (LICENSE / COPYING at the merge). With no licence found the package is built for the copyright
holder's own use and is marked not sellable.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

FORMAT = "knos-taskpack/1"
PROTECTED_DIRS = (".github/", ".knos/")
CHEAT_RULES = ("test_edited", "out_of_scope", "workflow_edited", "no_change", "patch_unreadable")
_TEST = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|_test\.[A-Za-z0-9]+$|\.test\.[A-Za-z0-9]+$|\.spec\.[A-Za-z0-9]+$|(^|/)conftest\.py$")
LICENCES = (    # (SPDX id, words that identify it in a licence file); first match wins
    ("AGPL-3.0", ("GNU AFFERO GENERAL PUBLIC LICENSE",)),
    ("LGPL-3.0", ("GNU LESSER GENERAL PUBLIC LICENSE",)),
    ("GPL-3.0", ("GNU GENERAL PUBLIC LICENSE", "Version 3")),
    ("GPL-2.0", ("GNU GENERAL PUBLIC LICENSE", "Version 2")),
    ("Apache-2.0", ("Apache License", "Version 2.0")),
    ("MPL-2.0", ("Mozilla Public License", "2.0")),
    ("BSD-3-Clause", ("Redistribution and use", "Neither the name")),
    ("BSD-2-Clause", ("Redistribution and use",)),
    ("ISC", ("Permission to use, copy, modify, and/or distribute",)),
    ("MIT", ("Permission is hereby granted, free of charge",)),
    ("Unlicense", ("This is free and unencumbered software",)),
)


class Refused(ValueError):
    """The export or check refused; the text says why."""


def is_test(path: str) -> bool:
    return bool(_TEST.search(path))


def canonical(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def spec_hash(manifest: dict) -> str:
    return hashlib.sha256(canonical({k: v for k, v in manifest.items() if k not in ("task_id", "spec_sha256")})).hexdigest()


def _git(repo: Path, *args: str, binary: bool = False):
    got = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=120)
    if got.returncode != 0:
        raise Refused(f"git {' '.join(args[:2])}: {got.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return got.stdout if binary else got.stdout.decode("utf-8", "replace")


def _show(repo: Path, commit: str, path: str) -> bytes | None:
    got = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True, timeout=60)
    return got.stdout if got.returncode == 0 else None


def licence(repo: Path, commit: str) -> dict:
    names = [n for n in _git(repo, "ls-tree", "--name-only", commit).splitlines() if re.match(r"(?i)^(licen[cs]e|copying)(\.[a-z]+)?$", n)]
    for name in names:
        text = (_show(repo, commit, name) or b"").decode("utf-8", "replace")
        for spdx, words in LICENCES:
            if all(w.lower() in text.lower() for w in words):
                return {"spdx": spdx, "file": name, "sellable": True,
                        "why": f"{spdx}: the licence travels with the package and its terms bind the buyer"}
        return {"spdx": None, "file": name, "sellable": False, "why": f"{name} names no licence Knos recognises: a person must read it before any sale"}
    return {"spdx": None, "file": None, "sellable": False,
            "why": "no licence file: only the copyright holder may use this code, so the package is for the holder's own use and is not sellable"}


def opt_in(repo: Path, commit: str, flag: bool, who: str = "") -> dict:
    raw = _show(repo, commit, ".knos/taskpack.yml")
    if raw is not None and re.search(r"(?m)^\s*export:\s*true\s*$", raw.decode("utf-8", "replace")):
        return {"how": ".knos/taskpack.yml export: true at the merge commit", "by": "the repository"}
    if flag:
        return {"how": "--opt-in given by the maintainer who ran the export", "by": who or "the maintainer running the export"}
    raise Refused("no maintainer opt-in: commit .knos/taskpack.yml with `export: true`, or run the export yourself as the maintainer with --opt-in")


def _tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for name in sorted(files):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode, info.uid, info.gid, info.uname, info.gname = len(files[name]), 0, 0o644, 0, 0, "", ""
            t.addfile(info, io.BytesIO(files[name]))
    return buf.getvalue()


def untar(blob: bytes) -> dict[str, bytes]:
    out = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r") as t:
        for m in t.getmembers():
            if not m.isfile() or m.name.startswith("/") or ".." in m.name.split("/"):
                raise Refused(f"the sealed archive holds an unsafe entry: {m.name[:80]}")
            got = t.extractfile(m)
            assert got is not None      # a regular file (checked above) always has contents to read
            out[m.name] = got.read()
    return out


def _seal(blob: bytes, key: bytes, aad: bytes) -> bytes:
    from .. import vault_crypto
    nonce = secrets.token_bytes(12)
    return nonce + vault_crypto.aead_seal(key, nonce, blob, aad)


def _open(blob: bytes, key: bytes, aad: bytes) -> bytes:
    from .. import vault_crypto
    return vault_crypto.aead_open(key, blob[:12], blob[12:], aad)


def scope_of(source_files: list[str]) -> list[str]:
    """Where a solution may write: the folder of each non-test file the fix changed ("" = the top folder's files)."""
    return sorted({p.rsplit("/", 1)[0] + "/" if "/" in p else "" for p in source_files})


def in_scope(path: str, scope: list[str]) -> bool:
    for s in scope:
        if s == "" and "/" not in path:
            return True
        if s and path.startswith(s):
            return True
    return False


def default_judge(test_files: list[str]) -> list[str]:
    if test_files and all(f.endswith(".py") for f in test_files):
        return ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "{tests}"]
    raise Refused("the hidden tests are not Python files: give the command that runs them with --test-cmd (use {tests} for their paths)")


def tree(repo: Path, commit: str, into: Path) -> None:
    """The repository's files at `commit`, unpacked into `into` (git archive: the repository itself is not touched). The
    commit's own bytes: with core.autocrlf on (Git for Windows' default) archive would write text files with CRLF line ends, and a
    patch made at the commit would not apply to them."""
    blob = _git(repo, "-c", "core.autocrlf=false", "archive", "--format=tar", commit, binary=True)
    into.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r") as t:
        for m in t.getmembers():
            if m.name.startswith("/") or ".." in m.name.split("/") or m.issym() or m.islnk():
                continue
            if hasattr(tarfile, "data_filter"):
                t.extract(m, into, filter="data")
            else:
                t.extract(m, into)


def run_judge(where: Path, judge: list[str], tests: list[str], timeout: float, run=subprocess.run) -> dict:
    """Run the locked judge command in `where`. Returns {passed, exit, summary}; the summary is the counts only (the
    output itself may quote a hidden test, so it is never kept)."""
    cmd = []
    for part in judge:
        if part == "{tests}":
            cmd += tests
        else:
            cmd.append(part.replace("{python}", sys.executable))
    from ..repro.run import clean_env
    env = clean_env()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        got = run(cmd, cwd=str(where), capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit": None, "summary": f"over {timeout:g} s"}
    counts = re.findall(r"(\d+) (passed|failed|errors?)", (got.stdout or "") + (got.stderr or ""))
    said = list(dict.fromkeys(f"{n} {w}" for n, w in counts))      # pytest says a count twice when tests error at collection
    return {"passed": got.returncode == 0, "exit": got.returncode, "summary": ", ".join(said) or f"exit {got.returncode}"}


def fee_terms(price_units: int | None) -> dict:
    """The fee split of a sale, from the one fee config (config/fees.yaml) through MONEY's API. The price is a founder
    decision: with none given, only where the split comes from is recorded."""
    try:
        from ..money import fees_config  # type: ignore[import-not-found]
    except ImportError:
        return {"source": "config/fees.yaml via knos.money.fees_config", "status": "knos.money is not in this install", "price": price_units}
    cfg = fees_config.load()
    if price_units is None:
        return {"source": "config/fees.yaml via knos.money.fees_config", "price": None, "status": "no price given"}
    split = cfg.task_package(int(price_units))
    return {"source": "config/fees.yaml via knos.money.fees_config", "price": int(price_units), "status": "computed", **split}


def export(repo: Path | str, *, merge: str, pr: dict, issue: dict, out: Path | str, opt_in_flag: bool = False, who: str = "",
           test_cmd: list[str] | None = None, timeout: float = 600, encrypt: bool = False, price_units: int | None = None,
           run=subprocess.run, now: Callable[[], float] = time.time) -> Path:
    """Build the package of the pull request merged at `merge`. `pr`: {repo, number}; `issue`: {number, title, body}.
    Returns the package's folder. Raises Refused for every rule a package keeps."""
    repo = Path(repo).resolve()
    merge = _git(repo, "rev-parse", f"{merge}^{{commit}}").strip()
    base = _git(repo, "rev-parse", f"{merge}^1").strip()
    who_opted = opt_in(repo, merge, opt_in_flag, who)
    rows = [ln.split("\t") for ln in _git(repo, "diff", "--name-status", "--no-renames", base, merge).splitlines() if ln.strip()]
    changed = [(r[0][0], r[-1]) for r in rows]
    tests = sorted(p for s, p in changed if is_test(p) and s != "D")
    source = sorted(p for s, p in changed if not is_test(p))
    if not tests:
        raise Refused("the merged fix adds or changes no test file: there is nothing to seal")
    if not source:
        raise Refused("the merged fix changes only tests: there is no task to solve")
    if any(p.startswith(PROTECTED_DIRS) for p in source):
        raise Refused("the fix changes .github/ or .knos/: a task package holds code fixes only")
    judge = list(test_cmd) if test_cmd else default_judge(tests)
    hidden = {p: _show(repo, merge, p) or b"" for p in tests}
    reference = _git(repo, "diff", "--binary", "--no-renames", base, merge, "--", *source)
    # the task is real: the hidden tests fail before the fix and pass after it
    with tempfile.TemporaryDirectory(prefix="knos-taskpack-") as tmp:
        before, after = Path(tmp) / "base", Path(tmp) / "merge"
        tree(repo, base, before)
        for p, blob in hidden.items():
            (before / p).parent.mkdir(parents=True, exist_ok=True)
            (before / p).write_bytes(blob)
        tree(repo, merge, after)
        began = time.monotonic()
        at_base = run_judge(before, judge, tests, timeout, run)
        at_merge = run_judge(after, judge, tests, timeout, run)
        took = round(time.monotonic() - began, 2)
    if at_base["passed"]:
        raise Refused("the hidden tests already pass before the fix: they do not test the issue")
    if not at_merge["passed"]:
        raise Refused(f"the hidden tests do not pass at the merge commit ({at_merge['summary']}): the judge command or the environment is wrong")
    tests_tar = _tar(hidden)
    ref_bytes = reference.encode("utf-8")
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "source": {"repo": pr["repo"], "pull_request": int(pr["number"]), "issue": issue.get("number"), "merge_commit": merge, "base_commit": base},
        "licence": licence(repo, merge),
        "opt_in": who_opted,
        "statement": {"title": str(issue.get("title") or ""), "body": str(issue.get("body") or "")},
        "scope": {"allowed": scope_of(source), "protected": list(PROTECTED_DIRS), "test_pattern": _TEST.pattern},
        "judge": {"command": judge, "timeout_seconds": timeout, "reward": "1.0 when every hidden test passes and no cheat rule fires, 0.0 when a test fails, -1.0 when a cheat rule fires (knos.referee.reward)"},
        "cheat_rules": list(CHEAT_RULES),
        "sealed": {"tests_sha256": hashlib.sha256(tests_tar).hexdigest(), "tests_count": len(tests),
                   "reference_sha256": hashlib.sha256(ref_bytes).hexdigest(), "encrypted": bool(encrypt)},
        "verified": {"base_fails": True, "merge_passes": True, "base_summary": at_base["summary"], "merge_summary": at_merge["summary"], "seconds": took},
        "fee": fee_terms(price_units),
        "sale": "nothing here offers or sells a task package",
        "made": int(now()),
    }
    manifest["spec_sha256"] = spec_hash(manifest)
    manifest["task_id"] = "knos-task-" + manifest["spec_sha256"][:16]
    folder = Path(out) / manifest["task_id"]
    (folder / "public").mkdir(parents=True, exist_ok=True)
    (folder / "sealed").mkdir(parents=True, exist_ok=True)
    if encrypt:
        key = secrets.token_bytes(32)
        aad = manifest["spec_sha256"].encode()
        (folder / "sealed" / "tests.tar.enc").write_bytes(_seal(tests_tar, key, aad))
        (folder / "sealed" / "reference.patch.enc").write_bytes(_seal(ref_bytes, key, aad))
        kf = Path(out) / f"{manifest['task_id']}.key"       # outside the package: shipping the folder never ships the key
        kf.write_text(key.hex() + "\n", encoding="ascii")
        try:
            os.chmod(kf, 0o600)
        except OSError:
            pass
    else:
        (folder / "sealed" / "tests.tar").write_bytes(tests_tar)
        (folder / "sealed" / "reference.patch").write_bytes(ref_bytes)
    (folder / "public" / "task.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "public" / "statement.md").write_text(statement(manifest), encoding="utf-8")
    return folder


def statement(manifest: dict) -> str:
    s, src = manifest["statement"], manifest["source"]
    where = ", ".join(f"`{a}`" if a else "the top folder's files" for a in manifest["scope"]["allowed"])
    return (f"# {s['title'] or 'Task'}\n\n{s['body'].strip()}\n\n---\n\nRepository {src['repo']} at commit `{src['base_commit']}`. "
            f"Change files in: {where}. Do not change tests, `.github/` or `.knos/`. "
            f"{manifest['sealed']['tests_count']} hidden test file(s) decide; you cannot see them.\n")


def load(pack: Path | str) -> dict:
    return json.loads((Path(pack) / "public" / "task.json").read_text(encoding="utf-8"))


def key_of(pack: Path, key_file: Path | None = None) -> bytes | None:
    kf = key_file or (Path(pack).parent / f"{Path(pack).name}.key")
    return bytes.fromhex(kf.read_text(encoding="ascii").strip()) if kf.is_file() else None


def sealed(pack: Path | str, name: str, key: bytes | None = None) -> bytes:
    """One sealed file's bytes ("tests.tar" or "reference.patch"), decrypted when the package is encrypted."""
    pack = Path(pack)
    m = load(pack)
    if m["sealed"]["encrypted"]:
        key = key or key_of(pack)
        if key is None:
            raise Refused("the package is encrypted and no key was given")
        return _open((pack / "sealed" / f"{name}.enc").read_bytes(), key, m["spec_sha256"].encode())
    return (pack / "sealed" / name).read_bytes()


def verify(pack: Path | str, key: bytes | None = None) -> list[str]:
    """Everything wrong with a package ([] when it checks): its spec hash and id, and each sealed file's sha256."""
    pack = Path(pack)
    try:
        m = load(pack)
    except (OSError, ValueError) as why:
        return [f"public/task.json cannot be read: {why}"]
    wrong = []
    if m.get("format") != FORMAT:
        wrong.append(f"not a {FORMAT} package")
    if m.get("spec_sha256") != spec_hash(m):
        wrong.append("the manifest does not hash to its spec_sha256: it was edited after export")
    if m.get("task_id") != "knos-task-" + str(m.get("spec_sha256"))[:16]:
        wrong.append("the task id is not derived from the spec hash")
    for name, field in (("tests.tar", "tests_sha256"), ("reference.patch", "reference_sha256")):
        try:
            blob = sealed(pack, name, key)
        except Refused as why:
            wrong.append(str(why))
            continue
        except Exception:  # noqa: BLE001 - a wrong key, a damaged file
            wrong.append(f"sealed/{name} cannot be opened (wrong key, or the file was changed)")
            continue
        if hashlib.sha256(blob).hexdigest() != m["sealed"].get(field):
            wrong.append(f"sealed/{name} does not hash to the manifest's {field}: it was changed")
    return wrong
