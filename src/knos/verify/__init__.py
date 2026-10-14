"""`knos verify`: before an agent opens a pull request, check the change the way a maintainer running Knos would,
and write a signed receipt to attach to it.

    1. The repository's AI policy, read at the BASE commit (AI_POLICY.md, CONTRIBUTING.md, ...: knos.verify.policy).
       A repository that bans AI-made work is refused: no tests run, no pull request should be opened. A conditional
       policy needs the person running the agent to confirm the condition (`--human-confirmed`).
    2. The cheat checks on the diff against the base (knos.verify.cheats: the referee's library when installed).
    3. The repository's own tests, at the committed HEAD, in a throwaway clone, twice by default (the re-run must
       agree). Uncommitted changes are not part of a pull request, so they are not verified (the receipt says when
       the tree had any). Tokens and secrets in the environment are not passed to the tests.
    4. A receipt (knos.verify.receipt): verdict, counts, cheat checks, hidden-test mode, the AI-use line, signed.

Hidden tests: when the repository runs Knos Gate (.knos/gate.yml at the base), its hidden tests run on the pull
request in the pinned workflow; this local receipt covers the public tests only and says so. Nothing here ever
reads or prints a hidden test.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from os import environ    # read whole once, in clean_env, to hand the tests everything but secrets
from pathlib import Path

from . import cheats, policy, receipt

BASES = ("origin/HEAD", "origin/main", "origin/master", "main", "master")
_SECRET_ENV = re.compile(r"TOKEN|SECRET|PASSW|PRIVATE|CREDENTIAL|API_?KEY|ACCESS_?KEY|SESSION|COOKIE|AUTH|^KNOS_(?!HOME$)|SIBYL_CRED", re.I)
_GH_REMOTE = re.compile(r"github\.com[:/]+([A-Za-z0-9][A-Za-z0-9-]{0,38}/[\w.-]{1,100}?)(?:\.git)?/?$")


class Cannot(Exception):
    """verify could not run at all (not a git repository, no commit). One sentence."""


def _git(tree: Path, *args: str, check: bool = True) -> str:
    got = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=120, check=False)
    if check and got.returncode != 0:
        raise Cannot(f"git {args[0]} failed: {(got.stderr or got.stdout).strip().splitlines()[-1:] or ['?']}")
    return got.stdout if got.returncode == 0 else ""


def _show(tree: Path, commit: str, name: str) -> str | None:
    got = subprocess.run(["git", "-C", str(tree), "show", f"{commit}:{name}"], capture_output=True, timeout=60, check=False)
    return got.stdout[:policy.MOST_BYTES].decode("utf-8", errors="replace") if got.returncode == 0 else None


def repo_name(tree: Path) -> str:
    url = _git(tree, "remote", "get-url", "origin", check=False).strip()
    m = _GH_REMOTE.search(url)
    return m.group(1) if m else ""


def _base(tree: Path, given: str) -> tuple[str, str]:
    """(the ref named, the merge-base commit of it and HEAD)."""
    for ref in ([given] if given else list(BASES)):
        mb = _git(tree, "merge-base", ref, "HEAD", check=False).strip()
        if mb:
            return ref, mb
    if given:
        raise Cannot(f"{given} is not a branch or commit this checkout knows; fetch it first (git fetch origin).")
    head = _git(tree, "rev-parse", "HEAD").strip()
    return "HEAD", head


def gate_config(text: str | None) -> dict:
    """What verify reads of .knos/gate.yml: {"on", "scope"}. Knos Gate's own loader when installed, else PyYAML,
    else only that the file exists."""
    if text is None:
        return {"on": False, "scope": []}
    data = None
    try:
        from ..gate import config as gate_cfg  # type: ignore[import-not-found]
        data = gate_cfg.parse(text)
    except Exception:  # noqa: BLE001 - not installed, or a different API: fall back
        try:
            import yaml  # type: ignore[import-untyped]
            data = yaml.safe_load(text)
        except Exception:  # noqa: BLE001
            data = None
    scope = []
    if isinstance(data, dict):
        raw = data.get("scope")
        if isinstance(raw, dict):
            raw = raw.get("allow") or raw.get("paths") or raw.get("allowed")
        if isinstance(raw, list):
            scope = [str(x) for x in raw if isinstance(x, str)]
    return {"on": True, "scope": scope}


def detect(tree: Path) -> list[str] | None:
    """The command that runs this repository's own tests, or None when none is found."""
    if (tree / "package.json").is_file():
        try:
            if (json.loads((tree / "package.json").read_text(encoding="utf-8")).get("scripts") or {}).get("test"):
                return ["npm", "test", "--silent"]
        except (ValueError, OSError, AttributeError):
            pass
    if (tree / "Cargo.toml").is_file():
        return ["cargo", "test", "--quiet"]
    if (tree / "go.mod").is_file():
        return ["go", "test", "./..."]
    py = any((tree / f).is_file() for f in ("pyproject.toml", "setup.cfg", "setup.py", "pytest.ini", "tox.ini"))
    if py or (tree / "tests").is_dir() or any(tree.glob("test_*.py")):
        return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if (tree / "Makefile").is_file() and re.search(r"^test:", (tree / "Makefile").read_text(encoding="utf-8", errors="replace"), re.M):
        return ["make", "test"]
    return None


def clean_env() -> dict:
    """The environment the tests get: this one without anything that looks like a token, key or secret."""
    env = {k: v for k, v in environ.items() if not _SECRET_ENV.search(k)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


_COUNTS = (     # the most specific first: cargo's and jest's lines also hold "N passed"
    (re.compile(r"test result: \w+\. (\d+) passed"), re.compile(r"; (\d+) failed"), None),                       # cargo
    (re.compile(r"Tests:.*?(\d+) passed"), re.compile(r"Tests:.*?(\d+) failed"), None),                           # jest
    (re.compile(r"(\d+) passed"), re.compile(r"(\d+) failed"), re.compile(r"(\d+) errors?\b")),                 # pytest
)


def counts(output: str) -> dict:
    """{"passed", "failed"} as the runner printed them, or None each when it printed neither."""
    for p_re, f_re, e_re in _COUNTS:
        p = [int(x) for x in p_re.findall(output)]
        if p:
            f = sum(int(x) for x in f_re.findall(output)) + (sum(int(x) for x in e_re.findall(output)) if e_re else 0)
            return {"passed": sum(p) if p_re.pattern.startswith("test result") else p[-1], "failed": f}
    return {"passed": None, "failed": None}


def run_tests(tree: Path, command: list[str], timeout: int) -> dict:
    t0 = time.monotonic()
    try:
        got = subprocess.run(command, cwd=str(tree), capture_output=True, text=True, encoding="utf-8", errors="replace",
                             env=clean_env(), timeout=timeout, check=False)
        code, output = got.returncode, (got.stdout or "") + (got.stderr or "")
    except subprocess.TimeoutExpired:
        code, output = None, ""
    except OSError as why:
        code, output = 127, str(why)
    return {"exit": code, **counts(output), "seconds": round(time.monotonic() - t0, 2),
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(), "timed_out": code is None}


def _clone(tree: Path, commit: str) -> Path:
    where = Path(tempfile.mkdtemp(prefix="knos-verify-"))
    subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(tree), str(where / "t")], check=True,
                   capture_output=True, timeout=300)
    subprocess.run(["git", "-C", str(where / "t"), "checkout", "-q", "--detach", commit], check=True, capture_output=True, timeout=300)
    return where


def verify(tree: Path, *, base: str = "", tests: str = "", runs: int = 2, ai_used: bool = True, agent: str = "",
           human_confirmed: bool = False, timeout: int = 900, repo: str = "", sign: bool = True, record: bool = True,
           runner=None) -> dict:
    """The receipt for the committed HEAD of the checkout at `tree`. `runner(tree, command, timeout) -> run dict` is
    given by tests; otherwise run_tests."""
    tree = Path(tree).expanduser().resolve()
    if not tree.is_dir():
        raise Cannot(f"{tree} is not a folder.")
    top = Path(_git(tree, "rev-parse", "--show-toplevel").strip())
    head = _git(top, "rev-parse", "HEAD").strip()
    dirty = bool(_git(top, "status", "--porcelain", "--untracked-files=no", check=False).strip())
    ref, base_commit = _base(top, base)
    name = repo or repo_name(top)
    pol = policy.read(get=lambda f: _show(top, base_commit, f))
    gate = gate_config(_show(top, base_commit, ".knos/gate.yml"))
    diff = _git(top, "diff", "--no-color", "-M", f"{base_commit}..{head}", check=False)
    changed = [x for x in _git(top, "diff", "--name-only", f"{base_commit}..{head}", check=False).splitlines() if x]
    reasons: list[str] = []
    findings, engine = cheats.scan(diff, base_dir=None, scope=gate["scope"])
    allowed = policy.may_open_pr(pol["stance"], human_confirmed)
    command = shlex.split(tests) if tests else None
    run_rows: list[dict] = []
    if not allowed:
        verdict = "refused"
        reasons.append("the repository's AI policy bans AI-made pull requests: do not open one" if pol["stance"] == "banned" else
                       "the repository accepts AI-made work only on a condition a person must confirm (--human-confirmed)")
    else:
        if not changed:
            reasons.append("no change against the base: nothing to verify")
        where = _clone(top, head)
        try:
            checkout = where / "t"
            command = command or detect(checkout)
            if command is None:
                reasons.append("no test command found: pass --tests")
            else:
                go = runner or run_tests
                run_rows = [go(checkout, command, timeout) for _ in range(max(1, runs))]
        finally:
            shutil.rmtree(where, ignore_errors=True)
        if run_rows and any(r["exit"] != 0 for r in run_rows):
            reasons.append("the tests failed" if run_rows[0]["exit"] not in (None,) else "the tests timed out")
        if cheats.refused(findings):
            reasons.append("cheat checks fired: " + ", ".join(sorted({f["rule"] for f in findings if f["severity"] == "refuse"})))
        verdict = "pass" if not reasons and run_rows else "fail"
    rerun_match = len(run_rows) > 1 and all((r["exit"], r["passed"], r["failed"]) == (run_rows[0]["exit"], run_rows[0]["passed"], run_rows[0]["failed"]) for r in run_rows)
    if len(run_rows) > 1 and not rerun_match:
        reasons.append("the re-run did not agree with the first run")
        verdict = "fail" if verdict == "pass" else verdict
    shown = [("python" if c == sys.executable else c) for c in command] if command else None    # no local path in a public receipt
    spec = {"command": shown, "base": base_commit, "gate": hashlib.sha256((_show(top, base_commit, ".knos/gate.yml") or "").encode()).hexdigest(),
            "scope": gate["scope"]}
    out = {
        "kind": receipt.KIND, "v": receipt.VERSION, "repo": name, "commit": head, "base": base_commit, "base_ref": ref,
        "changed_files": len(changed), "dirty_tree_not_verified": dirty,
        "spec_hash": "sha256:" + hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest(),
        "tests": {"command": shlex.join(shown) if shown else None, "runs": run_rows, "rerun_match": rerun_match if len(run_rows) > 1 else None},
        "hidden": ({"count": 0, "mode": "public tests only", "note": "Knos Gate is on for this repository: its hidden tests run on the pull request, not here."}
                   if gate["on"] else {"count": 0, "mode": "public tests only", "note": "The repository has no Knos Gate: only its public tests were run."}),
        "cheat_checks": {"engine": engine, "findings": findings},
        "ai_policy": {"stance": pol["stance"], "file": pol["file"], "source": pol["source"], "untrusted": pol["untrusted"]},
        "ai_disclosure": policy.disclosure(pol["stance"], agent, ai_used),
        "runner": {"where": "local", "attestation": "none: a local run, self-reported by this machine", "os": platform.system(),
                   "python": platform.python_version(), "knos": _version()},
        "verdict": verdict, "reasons": reasons, "made_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    signed = receipt.sign(out) if sign else out
    if record:
        _record(signed)
    return signed


def _version() -> str:
    from .. import version
    return version()


def _record(r: dict) -> None:
    """One `verification` entry in Knos Record (knos.record, which also writes it to Sibyl), when this install has it.
    Public fields only: hashes, verdict, cheat categories."""
    try:
        from .. import record  # type: ignore[attr-defined]
        record.append("verification", {"spec_hash": r["spec_hash"], "passed": r["verdict"] == "pass", "verdict": r["verdict"],
                                        "repo": r["repo"], "commit": r["commit"],
                                        "cheat": sorted({f["category"] for f in r["cheat_checks"]["findings"] if f["severity"] == "refuse"}),
                                        "receipt": (r.get("signature") or {}).get("digest", ""), "source": "knos verify"})
    except Exception:  # noqa: BLE001 - the record is a convenience here; the receipt is the deliverable
        pass
