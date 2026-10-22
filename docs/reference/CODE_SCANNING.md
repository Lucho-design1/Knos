# Knos Gate in GitHub's own places: code scanning, annotations, attestations, a required check

Knos Gate refuses a pull request that cheats (edits a test, touches a workflow, writes outside the scope the
maintainer set). Since 0.3.31 each refused finding also appears where a maintainer already looks on GitHub, and a
maintainer can make the check required in one command.

Everything here is off unless you turn it on, except the line annotations, which cost nothing.

| what | where it shows | how to turn it on | GitHub documentation (read 14 Oct 2026) |
| --- | --- | --- | --- |
| line annotations | on the "Knos Gate" check, at the first line the pull request changed in each refused file | on by default (Action: `::error` workflow commands; App: `output.annotations` of the check run, 50 per request) | [Checks API](https://docs.github.com/en/rest/checks/runs) |
| code-scanning alerts | the Security tab and the pull request's "Code scanning" section | Action input `code-scanning: "true"` and `permissions: security-events: write`; the App uploads when it holds `security_events: write` (in its manifest since 0.3.31) | [SARIF upload](https://docs.github.com/en/rest/code-scanning/code-scanning#upload-an-analysis-as-sarif-data), [SARIF support](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning) |
| receipt attestation | `gh attestation verify receipt.json -R OWNER/REPO` | Action input `attest: "true"` and `permissions: id-token: write, attestations: write` (public repositories, or private ones on GitHub Enterprise Cloud) | [artifact attestations](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds) |
| required check | the branch's merge box: "Knos Gate" must pass | `knos gate require OWNER/REPO --apply` (a token with administration on the repository; without `--apply` it prints the ruleset and changes nothing) | [Rulesets](https://docs.github.com/en/rest/repos/rules) |

## What is in the SARIF log

`knos gate run` writes `knos-gate.sarif` (SARIF 2.1.0) and `annotations.json` beside `verdict.json`
(`src/knos/gate/sarif.py`). One result per finding whose severity is `refuse`, at the first line the pull request
added in that file (line 1 for a file it only removed from).

Each result carries `partialFingerprints.knosFinding/v1`, a hash of the rule and the path, so the same cheat on the
next push stays the same alert. A passing run uploads an empty log, which closes the alerts an earlier push opened.
The log's `automationDetails.id` is `knos-gate/`, so Gate's analyses never mix with CodeQL's.

Nothing in the log is new information: it holds the rule, the category, the path and the sentence the comment
already shows. Like the comment, its text is checked against the hidden tests' lines before it is written; a log that
would quote one is replaced by an empty one.

## The attestation

With `attest: "true"` the Action runs `actions/attest` (pinned to v4.2.2) with the signed receipt as both subject and
predicate (predicate type `https://github.com/drexthealpha/Knos/blob/main/docs/reference/RECEIPT.md#knos-receipt-v1`).
The receipt's own ed25519 signature says which key signed it; the attestation adds a Sigstore record that this
repository's workflow produced exactly these bytes. Anyone checks it with:

```
gh attestation verify receipt.json -R OWNER/REPO --predicate-type https://github.com/drexthealpha/Knos/blob/main/docs/reference/RECEIPT.md#knos-receipt-v1
```

## Not shown live

These features were tested against recorded GitHub request shapes (`tests/test_gate_sarif.py`), not by uploading to a
live repository: the Knos rules for this version allow writes only to branches, pull requests and issues of the test
repository. The first maintainer who turns on `code-scanning` is the first live run.
