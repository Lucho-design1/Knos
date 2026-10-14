"""The reusable knos-outcome.yml and the buyer's prove.yml that calls it: who can mint a token, what is pinned, and the
audience check the signing job applies (the same rule as `python -m knos.outcomes check-audience`)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from knos.outcomes import __main__ as entry
from knos.outcomes import escrow, measure, synth

ROOT = Path(__file__).resolve().parents[1]
REUSABLE = ROOT / ".github" / "workflows" / "knos-outcome.yml"
PROVE = ROOT / "examples" / "outcomes" / "measured-support" / "prove.yml.in"
# the signing and measuring steps run on ubuntu-24.04 (GNU bash, coreutils); a Windows runner's `bash` may be another
# system's, and macOS has no sha256sum, so the two tests that run those steps' shell run where the workflow runs
GNU_SHELL = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="the workflow's shell is GNU bash on Linux")


def _doc(path: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["on"] = doc.pop(True, doc.get("on"))
    return doc


def test_the_reusable_workflow_measures_and_mints_nothing():
    doc = _doc(REUSABLE)
    assert set(doc["on"]) == {"workflow_call"} and doc["permissions"] == {}
    assert set(doc["on"]["workflow_call"]["outputs"]) == {"passed", "audiences", "result_hash"}
    jobs = doc["jobs"]
    assert list(jobs) == ["measure"] and jobs["measure"]["permissions"] == {"contents": "read"}
    text = REUSABLE.read_text(encoding="utf-8")
    assert "id-token" not in "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    run = "\n".join(s.get("run", "") for s in jobs["measure"]["steps"])
    assert 'python -m knos.outcomes measure "$SPEC" --lock "$LOCK" --repo .' in run and 'exit "$rc"' in run
    assert "persist-credentials: false" in text


def test_every_action_is_pinned_to_a_commit_listed_in_the_pins():
    pins = set(json.loads((ROOT / "scripts" / "action_pins.json").read_text(encoding="utf-8"))["pins"].values())
    for f in (REUSABLE, PROVE):
        for name, ref in re.findall(r"uses:\s*([\w./-]+)@(\S+)", f.read_text(encoding="utf-8")):
            assert re.fullmatch(r"[0-9a-f]{40}", ref) and ref in pins, (f.name, name, ref)


def test_prove_yml_signs_only_after_a_pass_and_only_in_its_own_job():
    doc = _doc(PROVE)
    assert PROVE.name == "prove.yml.in" and "Install it as .github/workflows/prove.yml" in PROVE.read_text(encoding="utf-8")   # knos_pay reads the file name
    assert doc["permissions"] == {}
    m, s = doc["jobs"]["measure"], doc["jobs"]["sign"]
    assert m["uses"].endswith("knos-outcome.yml") and m["permissions"] == {"contents": "read"}
    assert s["needs"] == "measure" and s["if"] == "needs.measure.outputs.passed == 'true'"
    assert s["permissions"] == {"contents": "read", "id-token": "write"}
    script = "\n".join(st.get("run", "") for st in s["steps"])
    assert not re.search(r"\bpython3?\b|\bpip\b|\s\./", script)     # runs no code from the repository
    assert "knos3:pay:" in script and "outcome.lock.json" in script and "knos-outcome:result:$RESULT" in script


def _world():
    s = synth.example_spec()
    lock = measure.lock_for(s, [], escrow.orders(s))
    return s, lock


def test_the_audience_check_takes_a_tiers_audience_and_refuses_every_other():
    s, lock = _world()
    o = escrow.orders(s)[1]
    good = measure.audience(o["address"], "a" * 40, bytes.fromhex(o["terms_hash"]), 0, s["escrow"]["issue"], measure.payees_text(s))
    assert entry.check_audience(s, lock, good) == []
    other_terms = measure.audience(o["address"], "a" * 40, bytes.fromhex(escrow.orders(s)[0]["terms_hash"]), 0, 1, measure.payees_text(s))
    assert entry.check_audience(s, lock, other_terms) == ["the terms hash is not that tier's"]
    thief = good.replace(s["parties"]["seller"]["address"], "11111111111111111111111111111111")
    assert entry.check_audience(s, lock, thief) == ["the payee is not the spec's seller"]
    stranger = good.replace(o["address"], "11111111111111111111111111111111")
    assert entry.check_audience(s, lock, stranger) == ["the order is not one of the lock's tiers"]
    assert entry.check_audience(s, lock, "knos3:pay:x") == ["not a knos3:pay audience with one payee"]


@GNU_SHELL
def test_the_signing_jobs_bash_rule_matches_the_python_rule():
    """The regular expression in prove.yml's sign step, run by bash on the same audiences."""
    s, lock = _world()
    o = escrow.orders(s)[0]
    good = measure.audience(o["address"], "a" * 40, bytes.fromhex(o["terms_hash"]), 0, s["escrow"]["issue"], measure.payees_text(s))
    rx = re.search(r'\[\[ "\$aud" =~ (\^knos3:pay:.*\$) \]\]', PROVE.read_text(encoding="utf-8")).group(1)
    for aud, ok in ((good, True), (good + ":", False), (good.replace(":0:", ":1:", 1), False), ("knos3:pay:" + "1" * 40, False)):
        done = subprocess.run(["bash", "-c", f'[[ "$1" =~ {rx} ]]', "_", aud], check=False)
        assert (done.returncode == 0) == ok, aud
    assert lock["payee"] == good.rsplit(":", 1)[1]


def test_the_stdlib_entry_point_measures_and_lists_audiences(tmp_path, capsys):
    from knos.outcomes import yamlish
    s, _ = _world()
    p = tmp_path / "outcome.yaml"
    p.write_text(yamlish.dumps(s), encoding="utf-8")
    rows = synth.tickets(s, 3000, seed=4)
    data = tmp_path / "t.csv"
    data.write_text(synth.to_csv(rows), encoding="utf-8")
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(measure.lock_for(s, [], escrow.orders(s))), encoding="utf-8")
    out = tmp_path / "r.json"
    rc = entry.main(["measure", str(p), "--lock", str(lock), "--data", str(data), "--out", str(out)])
    r = json.loads(out.read_text())
    assert rc == (0 if r["passed"] else 1)
    capsys.readouterr()
    assert entry.main(["audiences", str(out)]) == 0
    assert json.loads(capsys.readouterr().out) == [t["audience"] for t in r["tiers"] if t["passed"]]


DEMO = ROOT / "examples" / "outcomes" / "measured-support"


def test_the_devnet_demo_record_is_consistent_paid_where_measured_refunded_elsewhere():
    """demo.json is what `demo.py status` read from devnet after the demo: each tier the measurement passed was paid,
    each other tier was refunded, the amounts add up to the cap, and it says SYNTHETIC."""
    from knos.outcomes import spec as S
    doc = json.loads((DEMO / "demo.json").read_text(encoding="utf-8"))
    s = S.load(DEMO / "outcome.yaml.in")
    assert doc["synthetic"] is True and "SYNTHETIC" in doc["what"] and doc["cluster"] == "devnet"
    assert doc["spec_hash"] == S.spec_hash(s) and doc["measurement"]["passed"] is True
    assert sum(t["amount"] for t in doc["tiers"]) == S.micro(s["price"]["cap"])
    for t in doc["tiers"]:
        assert t["state"] == ("paid" if t["measured_pass"] else "refunded"), t
        assert re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{80,90}", t["pay_tx"] if t["measured_pass"] else t["refund_tx"])
    assert doc["seller_balance"] == sum(t["amount"] for t in doc["tiers"] if t["measured_pass"])



@GNU_SHELL
@pytest.mark.skipif(not shutil.which("sha256sum"), reason="coreutils' sha256sum, as on the ubuntu runner")
def test_the_workflows_shell_code_hash_is_the_packages_own(tmp_path):
    """knos-outcome.yml checks the measuring code with sha256sum before any of it runs; that hash must equal
    tamper.code_hash, or every honest run would stop."""
    from knos.outcomes import tamper
    step = next(st["run"] for st in _doc(REUSABLE)["jobs"]["measure"]["steps"] if "outside Python" in st.get("name", ""))
    line = next(ln.strip() for ln in step.splitlines() if ln.strip().startswith('got="$('))
    pkg = Path(tamper.__file__).parent
    script = f'dir="{pkg}"\n{line}\nprintf %s "$got"'
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    assert done.stdout == tamper.code_hash()
