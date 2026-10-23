"""Write a Sigstore client trust config for signing into Rekor v2: production's own (trusted root and signing config,
read fresh through TUF), plus the Rekor v2 log whose key that trusted root already holds. Sigstore's signing config
does not list a v2 log yet (signers opt in, https://blog.sigstore.dev/rekor-v2-ga/), so this names the newest v2 log
the trusted root has; verifying needs nothing but the production defaults.

    python scripts/rekor_v2_config.py <out.json>        then: sigstore --trust-config <out.json> sign --rekor-version 2 ...
"""
from __future__ import annotations

import json
import sys

from sigstore.models import ClientTrustConfig


def main(out: str) -> int:
    doc = json.loads(ClientTrustConfig.production()._inner.to_json())
    root, signing = doc["trustedRoot"], doc["signingConfig"]
    v2 = [t["baseUrl"] for t in root["tlogs"] if t["baseUrl"].startswith("https://log2")]    # the v2 shards: log<year>-<rev>
    if not v2:
        print("no Rekor v2 log in the production trusted root")
        return 1
    url = sorted(v2)[-1]
    if not any(s.get("majorApiVersion") == 2 for s in signing["rekorTlogUrls"]):
        start = next(t["publicKey"]["validFor"]["start"] for t in root["tlogs"] if t["baseUrl"] == url)
        signing["rekorTlogUrls"].insert(0, {"url": url, "majorApiVersion": 2, "validFor": {"start": start}, "operator": "sigstore.dev"})
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    print(f"Rekor v2 log: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
