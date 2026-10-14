"""Where re-runs happen: a Nebius Serverless Job when the account allows, else the local sandbox. Said, never hidden.

Serverless Jobs are driven by the Nebius AI Cloud CLI (`nebius ai job create|get|logs|delete`), authenticated by the
CLI's own profile and project id (~/.nebius/config.yaml), not by the Token Factory key. So a job runs only when the
operator opts in (KNOS_NEBIUS_JOBS=1) AND the `nebius` CLI is on PATH; otherwise every re-run is the local sandbox of
knos.autoresearch (a fresh directory, isolated Python, a hard time limit), and the output says which and why.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Callable


def backend(env=None, which: Callable[[str], str | None] = shutil.which) -> dict:
    env = os.environ if env is None else env
    if env.get("KNOS_NEBIUS_JOBS") == "1" and which("nebius"):
        return {"backend": "nebius-serverless-job", "reason": "KNOS_NEBIUS_JOBS=1 and the nebius CLI is installed"}
    why = []
    if env.get("KNOS_NEBIUS_JOBS") != "1":
        why.append("KNOS_NEBIUS_JOBS is not 1")
    if not which("nebius"):
        why.append("the nebius CLI is not installed")
    return {"backend": "local-sandbox", "reason": "; ".join(why) + " (Serverless Jobs need the CLI profile and project id)"}


def job_create(name: str, image: str, command: str, args: str, *, platform: str = "cpu-d3", preset: str = "4vcpu-16gb",
               timeout: str = "1h") -> list[str]:
    """The documented create command (docs.nebius.com/serverless/jobs/manage). Platform/preset are the CPU pair the
    Endpoints quickstart uses; check the account's quotas before the first job."""
    return ["nebius", "ai", "job", "create", "--name", name, "--image", image, "--container-command", command,
            "--args", args, "--platform", platform, "--preset", preset, "--timeout", timeout]


def run_job(name: str, image: str, command: str, args: str, *, runner=subprocess.run, poll_s: float = 10.0,
            max_wait_s: float = 3600.0, sleep=time.sleep) -> dict:
    """Create the job, wait until it leaves the running states, return its status text and logs. Live only."""
    def cli(*a):
        done = runner(["nebius", "ai", "job", *a] if a[0] != "create" else job_create(name, image, command, args),
                      capture_output=True, text=True, timeout=600)
        if done.returncode != 0:
            raise RuntimeError(f"nebius ai job {a[0]}: {done.stderr.strip()[-300:]}")
        return done.stdout.strip()

    cli("create")
    jid = cli("get-by-name", "--name", name, "--format", "jsonpath={.metadata.id}")
    waited, status = 0.0, ""
    while waited <= max_wait_s:
        status = cli("get", jid)
        if not any(s in status.upper() for s in ("PROVISIONING", "STARTING", "RUNNING", "PENDING")):
            break
        sleep(poll_s)
        waited += poll_s
    return {"job_id": jid, "status": status[-2000:], "logs": cli("logs", jid)[-20_000:]}
