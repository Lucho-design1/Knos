import io
import json
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knos_wanted import mock  # noqa: E402
from knos_wanted.qloo import ENDPOINTS  # noqa: E402


class FakeQloo:
    """A stand-in for Qloo's servers in tests: answers with the MOCK bodies (synthetic), or a chosen HTTP status per
    endpoint. Never real Qloo data."""

    def __init__(self, statuses=None):
        self.statuses = statuses or {}
        self.requests = []

    @staticmethod
    def endpoint_of(url):
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        ft = q.get("filter.type", "")
        for name, (path, fixed) in ENDPOINTS.items():
            if u.path != path:
                continue
            if name == "insights" and not ft.startswith("urn:entity"):
                continue
            if all(q.get(k) == v for k, v in fixed.items() if k != "feature.explainability"):
                return name, q
        return None, q

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        name, q = self.endpoint_of(req.full_url)
        st = self.statuses.get(name, 200)
        if st != 200:
            raise urllib.error.HTTPError(req.full_url, st, "x", {}, io.BytesIO(b"{}"))
        body = json.dumps(mock.respond(name, q)).encode()

        class R:
            status = 200

            def read(self):
                return body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()


@pytest.fixture
def fake():
    return FakeQloo


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for k in ("QLOO_API_KEY", "KNOS_WANTED_MOCK", "KNOS_WANTED_LLM_BASE_URL", "KNOS_WANTED_LLM_API_KEY", "KNOS_WANTED_LLM_MODEL",
              "KNOS_WANTED_DEVNET_KEYPAIR", "KNOS_WANTED_MINT", "QLOO_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KNOS_WANTED_CACHE", str(tmp_path / "cache" / "qloo"))
    monkeypatch.setenv("KNOS_WANTED_STATE", str(tmp_path / "state"))
