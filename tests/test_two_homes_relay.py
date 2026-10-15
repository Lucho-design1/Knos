"""The relay's pins (src/knos/settle/v2/relay/pins.py) know both homes of the rotate and claim workflows, exactly as the
0.3.35 programs do (tests/test_two_homes_rotate.py, tests/test_two_homes_claim.py): drexthealpha/knos-oidc-rotate and
Knos's branch `oidc-rotate`. Look-alikes and other cases are refused; the first deployment (v0) keeps the old home
only. Also: knos.mainnet_check takes a pinned commit from either home, and the relay reads key tokens in both."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from knos import mainnet_check as mc
from knos.proof import ghrelay
from knos.settle.v2 import oidc, relay
from knos.settle.v2.relay import jobs, pins

OLD = "drexthealpha/knos-oidc-rotate/.github/workflows/{}.yml@refs/heads/main"
KNOS = "drexthealpha/Knos/.github/workflows/{}.yml@refs/heads/oidc-rotate"
LOOK_ALIKES = ("someone/Knos/.github/workflows/{}.yml@refs/heads/main",
               "drexthealpha/Knos-x/.github/workflows/{}.yml@refs/heads/main",
               "drexthealpha/Knosx/.github/workflows/{}.yml@refs/heads/main",
               "drexthealpha/knos/.github/workflows/{}.yml@refs/heads/main",
               "DREXTHEALPHA/Knos/.github/workflows/{}.yml@refs/heads/main",
               "xdrexthealpha/Knos/.github/workflows/{}.yml@refs/heads/main",
               "drexthealpha/Knos/workflows/knos-oidc-rotate/.github/workflows/{}.yml@refs/heads/main",
               "evil/knos-oidc-rotate/.github/workflows/{}.yml@refs/heads/main")


def test_the_two_prefixes_are_exact():
    assert pins.ROTATE_REF_KNOS == "drexthealpha/Knos/.github/workflows/rotate.yml@"
    assert pins.CLAIM_REF_KNOS == "drexthealpha/Knos/.github/workflows/claim.yml@"
    assert relay.ROTATE_REFS == (relay.ROTATE_REF, relay.ROTATE_REF_KNOS) and relay.CLAIM_REFS == (relay.CLAIM_REF, relay.CLAIM_REF_KNOS)
    for home in (OLD, KNOS):
        assert pins.rotate_ref(home.format("rotate")) and pins.claim_ref(home.format("claim"))
        assert not pins.rotate_ref(home.format("claim")) and not pins.claim_ref(home.format("rotate"))
    for fake in LOOK_ALIKES:
        assert not pins.rotate_ref(fake.format("rotate")) and not pins.claim_ref(fake.format("claim")), fake
    for not_text in (None, 7, ["drexthealpha/Knos/.github/workflows/claim.yml@x"]):
        assert not pins.claim_ref(not_text) and not pins.rotate_ref(not_text)


def test_the_first_deployment_keeps_the_old_home_only():
    assert pins.rotate_ref(OLD.format("rotate"), 0) and not pins.rotate_ref(KNOS.format("rotate"), 0)
    assert pins.rotate_ref(KNOS.format("rotate"), 1)


def _key_token(ref: str, **over) -> SimpleNamespace:
    owner, repo = sorted(pins.ATTESTERS)[0]
    c = {"job_workflow_ref": ref, "job_workflow_sha": oidc.IDS["rotate_sha"], "runner_environment": "github-hosted",
         "repository_owner_id": owner, "repository_id": repo, "event_name": "schedule", "actor_id": owner, **over}
    return SimpleNamespace(c=c, issuer=oidc.GITHUB)


@pytest.mark.parametrize("v", [0, 1])
def test_the_relay_plans_an_attestation_from_either_home_where_the_program_takes_it(v):
    new = v >= 1
    assert jobs._attests(_key_token(OLD.format("rotate")), v) == (True, False)
    assert jobs._attests(_key_token(KNOS.format("rotate")), v) == (new, False)
    assert jobs._attests(_key_token(KNOS.format("rotate"), job_workflow_sha=oidc.IDS["rotate_sha2"]), v) == (new, False)
    by_hand = dict(event_name="workflow_dispatch")      # in an attester's repository by its owner: names, and (2.1) anyone's too
    assert jobs._attests(_key_token(KNOS.format("rotate"), **by_hand), v) == (new, new)
    for fake in LOOK_ALIKES:
        assert jobs._attests(_key_token(fake.format("rotate")), v) == (False, False), fake
    assert jobs._attests(_key_token(KNOS.format("rotate"), job_workflow_sha="2" * 40), v) == (False, False)


def test_mainnet_check_takes_a_pinned_commit_from_either_home():
    assert mc.PINS_REPOS == ("drexthealpha/knos-oidc-rotate", "drexthealpha/Knos")
    assert mc.PINS_REPO == mc.PINS_REPOS[0]


def test_the_relay_reads_key_tokens_in_both_homes():
    assert ghrelay.ROTATE_REPOS == (ghrelay.ROTATE_REPO, "drexthealpha/Knos")
    found = ghrelay.discover("2026-10-15T00:00:00Z", {}, getter=lambda path: {"items": []} if path.startswith("search/") else [])
    assert set(ghrelay.ROTATE_REPOS) <= found
