"""The demo record shipped in src/knos/record/demo/ (synthetic: every payload says so) and its anchor on Solana devnet.
Offline, its hashes and Merkle root are recomputed on every run. Reading devnet itself needs the network, which the
suite blocks: set RECORD_LIVE_DEVNET=1 to read the anchor transaction back from api.devnet.solana.com."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

import knos
from knos import record
from knos.record import anchoring, verifier

DEMO = Path(knos.__file__).parent / "record" / "demo"
ANCHOR_TX = "1C7bCGM7jHrj4XEkiWQKq3D4qYYj5mKxneGENJBjUoEEMzkQWHmRoaMMinkXePEpfS2A3E4vdWyfgEoB3m5qjFy"
ROOT = "2817c4837adc981d73cd676c73930deb998cde88e07fb27ba088ec005e54b599"
SIGNER = "8aukezen9sAALWShcZKK3hi8WawBi4vR6qmLf764PGBv"


def test_the_demo_record_is_synthetic_public_and_its_root_recomputes():
    lines = record.entries(DEMO)
    assert len(lines) == 10 and lines[-1]["kind"] == "anchor"
    assert all(e["payload"].get("synthetic") is True for e in lines[:-1])
    assert {e["tier"] for e in lines} == {"WARM", "COLD", "REFERENCE"}
    assert not list(DEMO.glob("sibyl.db*")) and not list(DEMO.glob("*.lock"))   # only the public file ships
    a = lines[-1]["payload"]
    assert (a["tx"], a["root"], a["signer"], a["cluster"], a["program"]) == (ANCHOR_TX, ROOT, SIGNER, "devnet", anchoring.MEMO_PROGRAM)
    assert record.merkle_root([e["hash"] for e in lines[:9]]) == ROOT
    rep = record.verify(DEMO, offline=True)
    assert rep["ok"] and rep["anchored"] == 9 and rep["unanchored"] == 1 and rep["sibyl"] == {"consulted": False}


@pytest.mark.skipif(os.environ.get("RECORD_LIVE_DEVNET") != "1", reason="reads Solana devnet; set RECORD_LIVE_DEVNET=1")
def test_the_demo_anchor_is_on_devnet(monkeypatch):
    monkeypatch.delattr(socket.socket, "connect", raising=False)       # the suite allows loopback only; this test reads devnet
    monkeypatch.setenv("KNOS_CLUSTER", "devnet")
    got = anchoring.chain_memo(ANCHOR_TX, anchoring.CLUSTERS["devnet"])
    assert got["found"] and got["err"] is None and SIGNER in got["signers"]
    assert anchoring.parse_memo(got["memo"])["root"] == ROOT
    rep = record.verify(DEMO)
    assert rep["ok"] and rep["anchors"][0]["chain"] == "ok", verifier.lines_of(rep)
