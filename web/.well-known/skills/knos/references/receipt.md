# The Knos verify receipt

`knos verify` writes one JSON object (default `.git/knos/receipt.json`, inside `.git` so it is never committed):

| Field | What it holds |
| --- | --- |
| `kind`, `v` | `knos-verify-receipt`, `1` |
| `repo`, `commit`, `base`, `base_ref` | the repository (from the `origin` remote), the verified HEAD, the merge base it was measured against |
| `spec_hash` | sha256 of what the check was: the test command, the base, the repository's `.knos/gate.yml` at the base, its scope |
| `tests` | the command, one row per run (`exit`, `passed`, `failed`, `seconds`, the sha256 of the output, never the output), `rerun_match` |
| `hidden` | `count` and `mode` only: a local receipt is always `public tests only`; hidden tests run in Knos Gate on the pull request |
| `cheat_checks` | `engine` (`knos.cheats` when the referee's library is installed, else `local`) and each finding: rule, category, path, severity |
| `ai_policy` | `stance` (banned, conditional, disclose, allowed, unstated), the file it came from, and the quoted lines inside `untrusted` |
| `ai_disclosure` | the AI-use line for the pull request's description |
| `runner` | `attestation: none: a local run, self-reported by this machine`, the OS, Python and knos versions |
| `verdict`, `reasons` | `pass`, `fail` or `refused`, and why |
| `signature` | `ed25519`, the signing key, the signature, and the digest (`sha256:` of the canonical JSON without `signature`) |

What the signature proves: the words were not changed after the key signed them. What it does not prove: that the
tests ran as described. A local run is self-reported. The receipt says so in `runner.attestation`.

Check one: `knos verify --check receipt.json` (exit 0 when the shape, digest and signature hold). Compare the
signing key with the one the author publishes (`knos verify --key` prints it).
