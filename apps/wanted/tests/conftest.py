import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knos_wanted.qloo_mcp import InProcess, Qloo  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """No network, no real key, no real Qloo: every test runs on Knos's MOCK MCP server (synthetic) unless it builds
    its own transport. Private folders go to tmp."""
    for k in ("QLOO_API_KEY", "KNOS_WANTED_LLM_BASE_URL", "KNOS_WANTED_LLM_API_KEY", "KNOS_WANTED_LLM_MODEL",
              "KNOS_WANTED_DEVNET_KEYPAIR", "KNOS_WANTED_MINT", "KNOS_WANTED_MOCK_FAIL", "QLOO_MCP_COMMAND", "QLOO_MCP_ARGS_JSON"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KNOS_WANTED_MOCK", "1")
    monkeypatch.setenv("KNOS_WANTED_SEED", "0")          # no seed crosses behind a test's back (a test of the seeds turns them on)
    monkeypatch.setenv("KNOS_WANTED_CACHE", str(tmp_path / "cache" / "qloo-mcp"))
    monkeypatch.setenv("KNOS_WANTED_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("KNOS_WANTED_RECORD", str(tmp_path / "record"))
    from knos_wanted import qloo_rest
    monkeypatch.setitem(qloo_rest._hold, "until", 0.0)      # a 429's pause in one test is not carried into the next


@pytest.fixture
def q():
    """The MOCK server in process (no Node needed), with no waiting between retries."""
    c = Qloo(InProcess(), mode="mock", reason="test", sleep=lambda s: None)
    yield c
    c.close()


@pytest.fixture
def pick():
    """Confirm the first candidate of every question (what a maker or buyer does by clicking)."""
    return lambda session: {qn["key"]: (qn["candidates"][0]["id"] if qn["pick"] == "one" else [qn["candidates"][0]["id"]])
                            for qn in session["questions"] if qn["candidates"]}

