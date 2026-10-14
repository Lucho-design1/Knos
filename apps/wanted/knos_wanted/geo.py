"""Geohash encode/decode (the public geohash algorithm; Qloo's heatmap cells carry a geohash)."""
from __future__ import annotations

_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(lat: float, lon: float, precision: int = 6) -> str:
    lat_r, lon_r = [-90.0, 90.0], [-180.0, 180.0]
    out, bit, ch, even = [], 0, 0, True
    while len(out) < precision:
        rng, v = (lon_r, lon) if even else (lat_r, lat)
        mid = (rng[0] + rng[1]) / 2
        if v >= mid:
            ch, rng[0] = (ch << 1) | 1, mid
        else:
            ch, rng[1] = ch << 1, mid
        even, bit = not even, bit + 1
        if bit == 5:
            out.append(_B32[ch])
            bit, ch = 0, 0
    return "".join(out)


def decode(gh: str) -> tuple[float, float]:
    lat_r, lon_r, even = [-90.0, 90.0], [-180.0, 180.0], True
    for c in gh.lower():
        v = _B32.index(c)
        for k in range(4, -1, -1):
            rng = lon_r if even else lat_r
            mid = (rng[0] + rng[1]) / 2
            if (v >> k) & 1:
                rng[0] = mid
            else:
                rng[1] = mid
            even = not even
    return (lat_r[0] + lat_r[1]) / 2, (lon_r[0] + lon_r[1]) / 2
