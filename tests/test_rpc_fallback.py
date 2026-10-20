"""knos.chain.call: public devnet answering 429 to the last retry hands the call to the second free devnet RPC."""
import io
import json
import urllib.error

from knos import chain


def test_devnet_429_falls_back_to_the_second_free_rpc(monkeypatch):
    asked = []

    def urlopen(req, timeout=10):
        asked.append(req.full_url)
        if req.full_url == chain.DEVNET_URL:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))
        return io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": 1, "result": 7}).encode())
    monkeypatch.setattr(chain.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(chain.time, "sleep", lambda s: None)
    assert chain.call(chain.DEVNET_URL, "getSlot", []) == 7
    assert asked.count(chain.DEVNET_URL) == 5 and asked[-1] == chain.DEVNET_FALLBACK


def test_another_cluster_is_never_redirected(monkeypatch):
    def urlopen(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))
    monkeypatch.setattr(chain.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(chain.time, "sleep", lambda s: None)
    try:
        chain.call("http://127.0.0.1:8899", "getSlot", [])
    except urllib.error.HTTPError as e:
        assert e.code == 429
    else:
        raise AssertionError("a local validator's 429 must not go to devnet")
