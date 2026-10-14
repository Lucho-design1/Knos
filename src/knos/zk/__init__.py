"""Knos ZK: prove a research result without revealing it.

A Groth16 proof over BN254 says "this submission got at least `threshold` right on the sealed hidden test set" while
the set and the submission stay private; only their salted MiMC commitments and the bar are public. The knos_zk
program checks the proof on Solana with the alt_bn128 syscalls and records a verdict account a payout can require.

  from knos.zk import groth16, mimc, client, bn254
  vk, proof, inputs = groth16.load_dir("zk/fixtures/score64")
  groth16.verify(vk, proof, inputs)            # off chain, pure Python
  client.verify_ix(program, proof, inputs)     # on chain

docs/reference/ZK.md says what is proven, the measured compute units, the devnet deployment and the limits (a TOY
setup: devnet only).
"""

from . import bn254, client, groth16, mimc  # noqa: F401

__all__ = ["bn254", "client", "groth16", "mimc", "record_verification"]


def record_verification(inputs: list[int], *, signature: str = "", program: str = "", passed: bool = True,
                        synthetic: bool = True, root=None) -> dict | None:
    """One COLD "verification" entry in Knos Record (public fields only: the two hashes, the bar, the devnet
    signature). None when knos.record is not installed."""
    try:
        from knos import record  # type: ignore[attr-defined]
    except ImportError:
        return None
    payload = {"zk": "groth16-bn254", "spec_hash": f"{inputs[0]:064x}", "pred_hash": f"{inputs[1]:064x}",
               "threshold": inputs[2], "passed": passed, "program": program, "tx": signature, "cluster": "devnet",
               "synthetic": synthetic}
    return record.append("verification", payload, root=root)
