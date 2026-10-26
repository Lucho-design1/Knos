"""What released a payout, read from the payout's own transaction logs (SYNTHETIC logs, shaped as devnet writes them)."""
from knos_wanted import server


def test_a_payout_says_what_released_it():
    referee = {"meta": {"logMessages": ["Program log: knos3:verdict order=X verdict=PASS evidence=ab have=1 of=1", "Program log: knos3:paid order=X"]}}
    github = {"meta": {"logMessages": [f"Program {server.OIDC_V2} invoke [1]", "Program log: knos2:paid"]}}
    assert server.released_by(referee) == "Released by the referee's verdict"
    assert server.released_by(github) == "Released by GitHub's signed check, verified on Solana"
    assert server.released_by({"meta": {"logMessages": ["Program log: something else"]}}) is None and server.released_by(None) is None
