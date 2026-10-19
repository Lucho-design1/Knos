# Keeping the app awake

The app (https://knos.onrender.com) runs on Render's free tier, which puts a web service to sleep after 15 minutes
without a request. A visitor then waits for a cold start, and so does a referee host polling `/api/referee/pending`.
A GitHub cron alone cannot keep it awake: on 18 Oct 2026 the 5-minute timer of `keepalive.yml` had not started a run
for more than four hours, while the always-on worker's chain kept running. Three pingers now hit `/healthz`, and the
first one does not depend on GitHub's timer.

| # | pinger | how often | what keeps it going |
|---|---|---|---|
| 1 | `.github/workflows/worker.yml`, job `healthz` | once per run of the chain, about every 4.5 minutes | each run starts the next; the watchdog revives the chain (below) |
| 2 | the referee PC daemon, `python -m knos.threshold serve --healthz-every 300` | every 5 minutes, on its own clock | the PC (host 3 of the FROST referee group) |
| 3 | `.github/workflows/keepalive.yml` | GitHub's `*/5` cron, when it fires | GitHub's timer |

## 1. The chain of runs

`worker.yml` is the relay's chain of runs. Each run relays for about 4.5 minutes, starts its successor 30 seconds
before it stops (`python -m knos.proof.chain start --after <run>`), and hands over. The chain's runs are
`workflow_dispatch` runs. The job `healthz` runs in every one of them (`if: github.event_name == 'workflow_dispatch'`):
`python3 -I src/knos/proof/chain.py healthz`. That is one GET of `/healthz`, tried up to 3 times 20 s apart, because a
cold start can take most of a minute. The job has no secret, read-only permission, a checkout of `src/knos/proof`
only, and installs nothing. It does not wait for the relay and the relay does not wait for it. A failed ping shows red
on the run and stops nothing.

## How the watchdog revives a stopped chain

A run that cannot relay starts no successor, so the chain can stop. `python -m knos.proof.chain watch` restarts it,
and it is called from three places:

1. **The run itself** (worker.yml, job `rewatch`). When a chain run's relay failed or was cancelled, the same run runs
   the watchdog as its own successor.
2. **The worker's timer and events** (worker.yml, job `watchdog`). GitHub's 5-minute cron starts it, and so does every
   event that starts worker.yml: a `knos-token` repository_dispatch, or a `knos` workflow run that ended.
3. **`watchdog.yml`.** It runs on `workflow_run` (a worker run that a person or another token started has ended), on
   a `knos-watch` repository_dispatch, and by hand.

A run counts as alive by its heartbeat, the relay job's `HEARTBEAT` step, which GitHub lists with the time it
completed. When no run holds the chain with a heartbeat in time, the watchdog cancels a stuck run and starts one. Two
watchdogs never start two chains: they share one concurrency group, and after a start the watchdog waits until GitHub
lists the new run. While the chain runs, so does pinger 1.

By hand: `gh workflow run watchdog.yml -R drexthealpha/Knos`, or start a first chain run with
`gh workflow run worker.yml -R drexthealpha/Knos`.

## 2. The PC daemon

The founder's PC runs host 3 of the referee group as a daemon:
`python -m knos.threshold serve --every 30 --healthz-every 300`. Every 30 s it polls the open signing sessions, and
every 300 s by its own clock it GETs `/healthz`. It logs one JSON line per ping, for example
`{"id": 3, "healthz": {"status": 200, "ms": 412}, "at": 1792345678}`, and a ping that fails logs
`"status": null` with the error's name. The daemon goes on either way.

## Limits

- GitHub disables a repository's scheduled workflows after 60 days with no activity in it. That stops pinger 3 and the
  cron path of the watchdog. It does not stop a chain that is running.
- Render's free tier gives 750 instance hours a month per workspace. One service awake all month uses about 744 of
  them. Only the app is kept awake.

Tests: `tests/test_threshold_codeattest.py` (the daemon's ping clock and its HTTP ping), `tests/test_keepalive_chain.py`
(chain.py's `healthz` against a local server that fails and then answers, and the job's shape in worker.yml).
