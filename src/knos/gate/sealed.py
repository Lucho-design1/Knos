"""Sealed hidden tests: a bundle the pull request's author cannot read, fixed by its hash, of which only counts leave.

    pack(folder) -> bytes          a deterministic tar.gz of the folder (sorted names, no owner, no time, no links)
    seal(bundle) -> str            its sha256: the value `hidden_tests.sha256` of .knos/gate.yml holds
    encode / decode                the bundle as one base64 line, the value of the repository secret
    unpack(bundle, dest, sha256)   refuses a bundle whose hash is not the seal, an absolute name, `..`, a link or a
                                   device; returns the paths it wrote (relative to dest)
    run(command, cwd, ...)         the suite on the pull request's tree, in a sandbox: an environment with no token
                                   and no secret, no network when the runner allows it (`sudo unshare --net`), its
                                   output kept in a file that is never printed; pytest's JUnit report gives the counts
    counts(junit_xml)              {"total","passed","failed","errors","skipped"} and nothing else: no test name, no
                                   message, no line of output
    leaks(text, files)             the lines of the hidden files (12 characters or more) a text would give away;
                                   everything Gate posts goes through it first

What the sandbox does not stop: the pull request's code runs in the same process as the hidden tests, so it can read
them while they run and can try to fake their result (its exit code and its report both come from that process). It has no network and no token to send them anywhere, its
output is never shown, and the cheat library refuses the edits that fake a result (runner_tampering,
runner_forgery). docs/reference/PR_GATE.md says this in its limits."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import os
import shlex
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BUNDLE = 48 * 1024        # a GitHub secret holds at most 48 KB; larger suites go in a private repository
_KEEP_ENV = ("PATH", "LANG", "LC_ALL", "PYTHONHASHSEED", "VIRTUAL_ENV", "PYTHONPATH")
# Windows cannot start Python without these (SYSTEMROOT for its crypto and sockets); none of them is a secret
_KEEP_ENV_NT = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "SYSTEMDRIVE", "PROGRAMDATA")


class Refused(ValueError):
    """The bundle is not the sealed one, or cannot be unpacked safely."""


def pack(folder: Path | str) -> bytes:
    root = Path(folder)
    if not root.is_dir():
        raise Refused(f"{folder} is not a folder")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for p in sorted(root.rglob("*"), key=lambda q: q.relative_to(root).as_posix()):
            rel = p.relative_to(root).as_posix()
            if any(part in ("__pycache__", ".pytest_cache") for part in rel.split("/")) or p.suffix == ".pyc":
                continue
            if p.is_symlink():
                raise Refused(f"{rel} is a link: a sealed bundle holds files only")
            if not p.is_file():
                continue
            data = p.read_bytes()
            info = tarfile.TarInfo(rel)
            info.size, info.mode, info.mtime, info.uid, info.gid, info.uname, info.gname = len(data), 0o644, 0, 0, 0, "", ""
            tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def seal(bundle: bytes) -> str:
    return hashlib.sha256(bundle).hexdigest()


def encode(bundle: bytes) -> str:
    return base64.b64encode(bundle).decode()


def decode(text: str) -> bytes:
    try:
        return base64.b64decode("".join(text.split()), validate=True)
    except ValueError:
        raise Refused("the hidden-test secret is not base64 (`knos gate seal DIR` prints the value to store)") from None


def unpack(bundle: bytes, dest: Path | str, sha256: str) -> list[str]:
    got = seal(bundle)
    if got != sha256:
        raise Refused(f"the hidden tests are not the sealed ones (sha256 {got[:12]}..., sealed {sha256[:12]}...)")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tar:
        for m in tar.getmembers():
            name = m.name
            if name.startswith("/") or ".." in name.split("/") or "\\" in name:
                raise Refused(f"the bundle names {name!r}, outside its folder")
            if not (m.isfile() or m.isdir()):
                raise Refused(f"the bundle holds {name!r}, which is not a file")
            if m.isdir():
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(m)
            target.write_bytes(f.read() if f else b"")
            written.append(name)
    return written


def hidden_lines(files: list[Path], min_len: int = 12) -> set[str]:
    out: set[str] = set()
    for f in files:
        try:
            text = Path(f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.update(s for s in (ln.strip() for ln in text.splitlines()) if len(s) >= min_len)
    return out


def leaks(text: str, lines: set[str]) -> list[str]:
    """The hidden lines `text` contains. Gate posts nothing that has one."""
    return sorted(ln for ln in lines if ln in text)


def counts(junit: Path | str | None) -> dict:
    """Counts from a JUnit XML report (pytest's --junitxml). A missing or unreadable report counts as one error."""
    if not junit or not Path(junit).is_file():
        return counts_bytes(None)
    return counts_bytes(_read_report(Path(junit)))


def counts_bytes(raw: bytes | None) -> dict:
    zero = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if raw is None:
        return {**zero, "errors": 1, "report": "missing"}
    if len(raw) > 20_000_000 or b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        return {**zero, "errors": 1, "report": "refused"}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return {**zero, "errors": 1, "report": "unreadable"}
    c: dict = dict(zero)
    for case in root.iter("testcase"):
        c["total"] += 1
        tags = {child.tag for child in case}
        if "failure" in tags:
            c["failed"] += 1
        elif "error" in tags:
            c["errors"] += 1
        elif "skipped" in tags:
            c["skipped"] += 1
        else:
            c["passed"] += 1
    c["report"] = "ok"
    return c


def sandbox_prefix(mode: str = "auto", env: dict | None = None) -> tuple[list[str], str]:
    """(argv prefix, what it is).
    `nonet,user`: a new network namespace (no network at all), run as KNOS_GATE_SANDBOX_USER, a user that cannot write
        the runner's files (so not $GITHUB_ENV, not $GITHUB_OUTPUT, not the Knos install the verdict is computed with)
        and cannot read the runner's processes; with exactly `env` and nothing else. actions/gate asks for this and
        nothing less: if it cannot be had, Gate does not run (fails closed).
    `nonet`: the same namespace as the runner's own user. `none`: no isolation beyond the clean environment (local runs
    and tests only). `auto`: the strongest of these the machine gives without a prompt."""
    if mode == "none":
        return [], "none"
    if mode not in ("auto", "nonet", "nonet,user"):
        raise Refused(f"unknown sandbox {mode!r} (nonet,user, nonet, auto or none)")
    sandbox_user = os.environ.get("KNOS_GATE_SANDBOX_USER", "")
    user = sandbox_user or os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    can = False
    if shutil.which("unshare") and shutil.which("sudo") and user:
        try:
            can = subprocess.run(["sudo", "-n", "unshare", "--net", "true"], capture_output=True, timeout=20).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            can = False
    if mode == "nonet,user" and not (can and sandbox_user):
        raise Refused("the sandbox (no network, a user of its own: KNOS_GATE_SANDBOX_USER) cannot be made on this runner, "
                      "so Gate does not run the pull request's code")
    if can:
        assigns = [f"{k}={v}" for k, v in sorted((env or {}).items())]
        kind = "nonet,user" if sandbox_user else "nonet"
        return ["sudo", "-n", "unshare", "--net", "--", "sudo", "-n", "-u", user, "--", "env", "-i", *assigns], kind
    if mode == "nonet":
        raise Refused("a sandbox with no network was asked for and this runner cannot make one (sudo unshare --net)")
    return [], "none"


def _read_report(path: Path, limit: int = 20_000_000) -> bytes | None:
    """The bytes of a report the sandbox wrote, read without following a link and only if it is a regular file."""
    import stat
    try:
        if stat.S_ISLNK(os.lstat(path).st_mode):        # Windows has no O_NOFOLLOW: say no to a link before opening
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return None
        with os.fdopen(fd, "rb", closefd=False) as f:
            return f.read(limit + 1)
    finally:
        os.close(fd)


def _own_file(path: Path):
    """A new file of the runner's, opened for writing: whatever was at `path` is removed first, and a link that
    appears in between is not followed (O_EXCL | O_NOFOLLOW)."""
    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    return os.fdopen(fd, "wb")


def run(command: str, cwd: Path | str, junit: Path | str | None = None, log: Path | str | None = None, *, timeout: int = 600,
        sandbox: str = "auto", extra_env: dict | None = None) -> dict:
    """Run `command` in `cwd` with a clean environment; pytest commands get --junitxml added. Returns counts(...) plus
    the exit code, the sandbox kind and seconds. A pass needs exit code 0 AND a clean report (`passed`).

    Where things are written: the sandbox gets a fresh private folder of its own (its HOME and its report), made for
    this run and removed after it. The runner never opens, changes or follows anything in it except to read the report
    (no link followed, regular files only). The output goes to `log`, a new file of the runner's (never printed).
    `junit` is not written: it is kept for callers and ignored."""
    import tempfile
    import time
    argv = split(command)
    if not argv:
        raise Refused("an empty test command")
    if log is None:
        raise Refused("a log path is needed")
    is_pytest = "pytest" in argv[0] or (len(argv) > 2 and argv[1] == "-m" and argv[2] == "pytest")
    box = Path(tempfile.mkdtemp(prefix="knos-gate-box-"))
    report = box / "report.xml"
    if is_pytest:
        argv += [f"--junitxml={report}", "-p", "no:cacheprovider"]
    keep = _KEEP_ENV + (_KEEP_ENV_NT if os.name == "nt" else ())
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update({"HOME": str(box), "CI": "true", "PYTHONDONTWRITEBYTECODE": "1", **(extra_env or {})})
    if os.name == "nt":
        env["USERPROFILE"] = str(box)
    t0 = time.monotonic()
    kind, code = "none", -1
    try:
        prefix, kind = sandbox_prefix(sandbox, env)
        sandbox_user = os.environ.get("KNOS_GATE_SANDBOX_USER", "") if kind == "nonet,user" else ""
        if sandbox_user:          # the box becomes the sandbox user's: the runner reads it and never writes into it
            subprocess.run(["sudo", "-n", "chown", sandbox_user, str(box)], check=True, capture_output=True, timeout=20)
            subprocess.run(["sudo", "-n", "chmod", "0755", str(box)], check=True, capture_output=True, timeout=20)
        with _own_file(Path(log)) as out:
            try:
                done = subprocess.run(prefix + argv, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=timeout)
                code = done.returncode
            except subprocess.TimeoutExpired:
                code = -9
            except FileNotFoundError:
                code = 127
        got = counts_bytes(_read_report(report)) if is_pytest else _from_exit(code)
        if is_pytest and got.get("report") != "ok" and code == 0:
            got = _from_exit(code)
    finally:
        if os.environ.get("KNOS_GATE_SANDBOX_USER") and kind == "nonet,user":
            subprocess.run(["sudo", "-n", "rm", "-rf", "--", str(box)], capture_output=True, timeout=60)
        shutil.rmtree(box, ignore_errors=True)
    got.update({"exit": code, "sandbox": kind, "seconds": round(time.monotonic() - t0, 2), "timed_out": code == -9})
    return got


def split(command: str) -> list[str]:
    """A command line as argv. POSIX rules everywhere but Windows, where a backslash is a path separator, not an
    escape (shlex's POSIX mode would turn C:\\py\\python.exe into C:pypython.exe): there the words are split as
    cmd does and the quotes around a word are taken off."""
    if os.name != "nt":
        return shlex.split(command)
    return [w[1:-1] if len(w) >= 2 and w[0] == w[-1] and w[0] in "\"'" else w for w in shlex.split(command, posix=False)]


def _from_exit(code: int) -> dict:
    """A command that is not pytest: one result, its exit code."""
    ok = code == 0
    return {"total": 1, "passed": int(ok), "failed": int(not ok), "errors": 0, "skipped": 0, "report": "exit-code"}


def passed(c: dict) -> bool:
    """A pass: the command exited 0 AND its report counts at least one passed test and no failure or error."""
    return bool(c) and c.get("exit", 0) == 0 and c.get("total", 0) > 0 and c.get("failed", 1) == 0 \
        and c.get("errors", 1) == 0 and c.get("passed", 0) > 0 and not c.get("timed_out")
