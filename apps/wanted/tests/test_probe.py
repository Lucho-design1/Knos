import json

import pytest

from knos_wanted import probe
from knos_wanted.qloo import ENDPOINTS, Qloo


def test_probe_records_status_codes_only(fake, tmp_path):
    f = fake({"heatmap": 403, "compare": 404})
    q = Qloo(api_key="secret-key", opener=f, cache_dir=tmp_path / "qloo", unserved=set())
    out = tmp_path / "probe.json"
    got = probe.run(q, out)
    assert set(got["endpoints"]) == set(ENDPOINTS)
    assert got["endpoints"]["heatmap"]["status"] == 403 and got["endpoints"]["search"]["status"] == 200
    text = out.read_text()
    saved = json.loads(text)
    for v in saved["endpoints"].values():
        assert set(v) == {"status"}
    assert "synthetic" not in text and "mock-" not in text and "secret-key" not in text   # no response data, no key
    assert not list((tmp_path / "qloo").glob("*.json"))                                   # the probe caches nothing
    assert Qloo(api_key="k", cache_dir=tmp_path / "qloo").unserved == {"heatmap", "compare"}


def test_probe_needs_key():
    with pytest.raises(SystemExit):
        probe.run(Qloo())
