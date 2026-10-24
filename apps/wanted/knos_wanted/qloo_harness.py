"""Qloo's harness as the demand check's first surface (kit docs/API_ACCESS.md: `qloo api` is a supported surface).

One long-lived `qloo api mcp` process (the harness's endpoint-shaped MCP server, JSON-RPC over stdio) answers every call
whose parameters map one to one onto a harness tool's arguments; it returns Qloo's own answer body. A call that needs a
parameter the harness does not take (a popularity floor, a trend bias, diversification, a tag filter ...) goes to the
REST API as before, so no answer changes; each call's trace says which surface answered it.

The key reaches the harness only through its environment (QLOO_API_KEY), never a command line. Off when
KNOS_QLOO_HARNESS=0 or when the `qloo` command is not installed.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import sys
import subprocess
import threading
import time

SURFACE = "qloo api mcp (Qloo's harness)"
# the V8 heap of each Node process the app starts (Qloo's two harness servers): the free instance has 512 MB for all
NODE_HEAP = "--max-old-space-size=96"
START_S = 240.0         # the handshake's wait at a start: the free instance loads the harness slowly
MAX_STARTS = 3          # starts in a row whose handshake did not finish: then this process asks Qloo's REST API only
CALL_S = 20.0
# Qloo parameter -> harness argument, per endpoint: a call maps only when every parameter it sends is listed here
MAP = {
    "/v2/insights": ("qloo_insights", {"filter.type": "type", "signal.interests.entities": "signal_entities",
                                       "signal.interests.tags": "signal_tags", "filter.location.query": "filter_location",
                                       "take": "take"}),
    "/search": ("qloo_search", {"query": "query", "types": "type", "take": "take"}),
}


def mapped(path: str, params: dict) -> tuple[str, dict] | None:
    """(tool, arguments) when the harness can ask exactly this question, else None."""
    spec = MAP.get(path)
    if not spec or not params:
        return None
    tool, names = spec
    if any(k not in names for k in params):
        return None
    args = {names[k]: (int(v) if names[k] == "take" and str(v).isdigit() else v) for k, v in params.items()}
    return (tool, args) if "type" in args or tool == "qloo_search" else None


class Harness:
    def __init__(self, command: list[str] | None = None, env: dict | None = None, call_s: float = CALL_S):
        self.command, self.env, self.call_s = command, env, call_s
        self.server_info: dict = {}                   # the server's answer to initialize (name, version)
        self.starts = 0                               # starts in a row that did not finish the handshake
        self.proc: subprocess.Popen | None = None
        self.lock, self.n, self.answered = threading.Lock(), 0, 0
        self.failed_at: float | None = None           # never 0: a fresh machine's clock starts near 0
        self.starting = threading.Lock()              # held through the handshake: no question goes before it ends
        self.ready = False
        self.waiting: dict[int, list] = {}            # request id -> [event, answer]: many questions in flight at once

    def _cmd(self) -> list[str] | None:
        if self.command:
            return self.command
        q = (shutil.which("qloo.cmd") if os.name == "nt" else None) or shutil.which("qloo")     # Windows runs npm's .cmd shim
        return [q, "api", "mcp"] if q else None

    def enabled(self) -> bool:
        return os.environ.get("KNOS_QLOO_HARNESS", "1") != "0" and self._cmd() is not None and self.starts < MAX_STARTS

    def _read(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:                       # each answer to the request that carries its id
            try:
                m = json.loads(line)
            except ValueError:
                continue
            slot = self.waiting.get(m.get("id")) if isinstance(m, dict) else None
            if slot:
                slot[1] = m
                slot[0].set()
        for slot in list(self.waiting.values()):      # the harness stopped: nobody waits for it
            slot[0].set()

    def _send(self, method: str, params: dict | None = None, notify: bool = False) -> tuple[int, list] | None:
        with self.lock:
            proc = self.proc
            assert proc and proc.stdin
            self.n += 1
            sid = self.n
            slot = [threading.Event(), None]
            if not notify:
                self.waiting[sid] = slot
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}} | ({} if notify else {"id": sid})) + "\n")
            proc.stdin.flush()
        return None if notify else (sid, slot)

    def _wait(self, sent: tuple[int, list], timeout: float | None = None) -> dict:
        sid, slot = sent
        try:
            if not slot[0].wait(timeout or self.call_s) or slot[1] is None:
                raise TimeoutError("the harness did not answer in time")
            return slot[1]
        finally:
            self.waiting.pop(sid, None)

    def _ensure(self) -> None:
        if self.ready and self.proc is not None and self.proc.poll() is None:
            return
        with self.starting:
            if self.ready and self.proc is not None and self.proc.poll() is None:
                return
            # one harness process at most: one that never finished its handshake is stopped before the next starts (each
            # start had left one behind, 120 MB each, while the harness answered none of 24 Oct 2026's calls)
            self.stop(self.proc)
            if self.starts >= MAX_STARTS:
                raise OSError(f"the harness did not start {MAX_STARTS} times: REST only from now on")
            self.starts += 1
            self.ready = False
            self._start()
            self.ready = True
            self.starts = 0

    def _start(self) -> None:
        with self.lock:
            env = {**os.environ, **(self.env or {})}
            if env.get("QLOO_BASE_URL") and not env.get("QLOO_TRUSTED_BASE_URL"):
                env["QLOO_TRUSTED_BASE_URL"] = env["QLOO_BASE_URL"]   # the harness trusts only the endpoint it is told
            env.setdefault("NODE_OPTIONS", NODE_HEAP)                  # each Node process within its share of 512 MB
            # a session of its own: `qloo` is a launcher with a child server, and stopping the launcher alone left the
            # server (115 MB) running, one more at each restart (24 Oct 2026: six of them, 804 MB in all)
            self.proc = subprocess.Popen(self._cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                                         start_new_session=os.name != "nt")
            threading.Thread(target=self._read, args=(self.proc,), daemon=True, name="qloo-harness").start()
            threading.Thread(target=self._errors, args=(self.proc,), daemon=True, name="qloo-harness-stderr").start()
        t0 = time.monotonic()
        # its own, longer wait: the harness answers its handshake in 2.4 s on four cores and much later on the free
        # instance's share of one, where the 20 s of a call made every start time out (24 Oct 2026)
        got = self._wait(self._send("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                                   "clientInfo": {"name": "knos", "version": "1"}}), START_S)
        print(f"qloo harness: {' '.join(self._cmd() or [])[-24:]} started in {time.monotonic() - t0:.1f} s", file=sys.stderr, flush=True)
        self.server_info = ((got or {}).get("result") or {}).get("serverInfo") or {}
        self._send("notifications/initialized", notify=True)

    def _errors(self, proc: subprocess.Popen) -> None:
        """The harness's own error output, in this server's log (its first 40 lines): the reason it did not start is
        there, not in a timeout."""
        for n, line in enumerate(proc.stderr or []):
            if n < 40 and line.strip():
                print(f"qloo harness stderr: {line.rstrip()[:300]}", file=sys.stderr, flush=True)

    def warm(self) -> None:
        """Start the harness ahead of the first check (its start, not Qloo, is the slow part)."""
        if self.enabled():
            try:
                self._ensure()
            except (OSError, ValueError, TimeoutError, AssertionError):
                self.failed_at = time.monotonic()

    def call(self, tool: str, args: dict) -> dict | None:
        """Qloo's answer body from the harness, or None (not installed, failed in the last minute, or not answered)."""
        if not self.enabled() or (self.failed_at is not None and time.monotonic() - self.failed_at < 60):
            return None
        if not self.ready:                            # still starting: this call goes to REST, no check waits on it
            if not self.starting.locked():
                threading.Thread(target=self.warm, daemon=True, name="qloo-harness-warm").start()
            return None
        proc = None
        try:
            self._ensure()
            proc = self.proc                              # the process this question goes to: the one stopped if it fails
            res = (self._wait(self._send("tools/call", {"name": tool, "arguments": args})) or {}).get("result") or {}
            body = res.get("structuredContent")
            if body is None:
                text = "".join(c.get("text", "") for c in res.get("content") or [] if isinstance(c, dict))
                body = json.loads(text) if text.strip().startswith("{") else None
            if res.get("isError") or not isinstance(body, dict) or body.get("success") is False:
                text = "".join(c.get("text", "") for c in res.get("content") or [] if isinstance(c, dict))
                print(f"qloo harness: {tool} answered no result ({text[:120]!r}); REST for this call", file=sys.stderr, flush=True)
                return None
            self.answered += 1
            return body
        except (OSError, ValueError, TimeoutError, AssertionError) as why:
            self.failed_at = time.monotonic()
            print(f"qloo harness: {type(why).__name__}: {str(why)[:120]}; REST for a minute", file=sys.stderr, flush=True)
            # a slow answer is not a dead harness: under load every slow one restarted it, every ~20 s; it is stopped only
            # when it broke (a closed pipe, a bad line) or has exited
            if not isinstance(why, TimeoutError) or (proc is not None and proc.poll() is not None):
                self.stop(proc)
            return None

    def stop(self, proc: subprocess.Popen | None) -> None:
        """Stop the process a question failed on, and wait for it; the harness is started again only if that process was
        still the current one. Stopping whatever was current instead let a newer process be killed while the failed one
        (118 MB) kept running beside it: two `qloo api mcp` under load, 24 Oct 2026."""
        if proc is None:
            return
        with self.lock:
            if self.proc is proc:
                self.ready = False
                self.proc = None
        if proc.poll() is None:
            pid = getattr(proc, "pid", None)
            try:
                if os.name != "nt" and isinstance(pid, int):
                    os.killpg(os.getpgid(pid), signal.SIGKILL)      # the launcher and the server it started
                else:
                    proc.kill()
            except (ProcessLookupError, PermissionError):
                proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


_one: Harness | None = None


def harness() -> Harness:
    global _one
    if _one is None:
        _one = Harness()
    return _one
