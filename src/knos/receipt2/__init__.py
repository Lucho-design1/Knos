"""Knos Receipt for a pull request: signed (Ed25519), offline-verifiable, counts only. See knos.receipt2.core.

Not knos.receipt (the acceptance receipt of a paid order, docs/reference/RECEIPT.md): this one is what Knos Gate, or an
author's own public-tests run, says about one pull request at one commit, paid or not."""
from .core import build, canonical, digest, keygen, known_issuer, secrets_in, sign, verify  # noqa: F401
