"""The CODE referee's attestation: what proves that the milestone check ran as code, in GitHub Actions, at a known
commit, and reached the verdict the FROST hosts sign. No account anywhere: GitHub's OIDC token, Solana devnet, and
Sigstore's public-good instance (keyless).

Host 2 of the referee group (.github/workflows/referee.yml, job `sign`) runs the milestone check itself
(knos.threshold.check.milestone_digest). For every session whose digest it recomputed, it writes one VERDICT file:

    {"kind": "knos-code-referee-verdict", "v": 1, "session", "verdict": "PASS", "digest" (what the FROST group signs),
     "group_key", "order", "program", "stage", "claim", "evidence_url", "page_sha256", "evidence_hash",
     "check": "knos.threshold.check.milestone_digest",
     "github": {"repository", "workflow_ref", "sha", "run_id", "run_attempt"}}

as canonical JSON (sorted keys, no spaces). The job `attest` of the same run, which holds no key share, then:

  1. ATTESTATION. actions/attest-build-provenance signs a SLSA v1 provenance statement over the verdict files'
     sha256 (Sigstore keyless: a Fulcio certificate for the run's OIDC identity, logged in Rekor). `verify_bundle`
     checks it against Sigstore's public trust root (knos.sources.sigstore, the pinned root; sigstore-python for a
     log that adapter cannot read): the certificate's identity must be
     https://github.com/drexthealpha/Knos/.github/workflows/referee.yml@refs/heads/main, issued by GitHub Actions, at
     the verdict's commit, and the statement's subject must be the verdict's sha256.
  2. ON CHAIN. A GitHub OIDC token of the job with the audience `knos-referee:verdict:<sha256 of the verdict>` goes to
     the app server (POST /api/referee/attest). The server checks it (knos.threshold.ghoidc: referee.yml on main of
     drexthealpha/Knos by id), then has the DEPLOYED knos_oidc verify it on devnet (knos.settle.v2.relay.verify_only:
     Write + Step, RS256 under GitHub's key). The token account ["tok", relayer, sha256(token)] is then VERIFIED and
     holds the decoded claims: repository, workflow_ref, sha, run_id and the audience that names the verdict's hash.
     Anyone reads it from the chain (owner knos_oidc, `knos.settle.v2.oidc.read_token`).
  3. RELEASE. Unchanged: two of three FROST hosts sign the verdict's digest; the one group signature releases.

So a milestone page shows four things that each verify without Knos: the workflow run, the knos_oidc verification
transaction, the Sigstore attestation, and the FROST release transaction.

Only the standard library is imported here at module level (the attest job runs this with no install);
`verify_bundle` imports knos.sources.sigstore (standard library too) when it is called.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

KIND = "knos-code-referee-verdict"
V = 1
AUD_PREFIX = "knos-referee:verdict:"
ISSUER = "https://token.actions.githubusercontent.com"
REPOSITORY = "drexthealpha/Knos"
WORKFLOW_PATH = ".github/workflows/referee.yml"
IDENTITY = f"https://github.com/{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main"
SLSA_V1 = "https://slsa.dev/provenance/v1"
IN_TOTO = "application/vnd.in-toto+json"
API = "https://api.github.com"
MAX_VERDICT = 16_384
MAX_BUNDLE = 262_144


class AttestError(ValueError):
    pass


# -- the verdict file ---------------------------------------------------------------------------------------------------
def verdict(session: dict, digest: bytes, ev: dict, env=None) -> dict:
    """The code referee's verdict for one session, from this host's OWN check (`digest`, `ev`) and the run it is in."""
    env = os.environ if env is None else env
    req = session["request"]
    doc, stage = req["doc"], req["stage"]
    return {"kind": KIND, "v": V, "session": session["id"], "verdict": "PASS", "digest": digest.hex(), "group_key": session["group_key"],
            "order": doc["orders"][stage]["order"], "program": doc["program"], "stage": stage, "claim": doc["claim"]["id"],
            "evidence_url": req.get("evidence_url"), "page_sha256": ev.get("page_sha256"), "evidence_hash": ev.get("evidence_hash"),
            "check": "knos.threshold.check.milestone_digest",
            "github": {"repository": env.get("GITHUB_REPOSITORY"), "workflow_ref": env.get("GITHUB_WORKFLOW_REF"), "sha": env.get("GITHUB_SHA"),
                       "run_id": str(env.get("GITHUB_RUN_ID") or ""), "run_attempt": str(env.get("GITHUB_RUN_ATTEMPT") or "")}}


def canonical(rec: dict) -> bytes:
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audience(verdict_bytes: bytes) -> str:
    return AUD_PREFIX + sha256_hex(verdict_bytes)


def write(rec: dict, folder: str | Path) -> Path:
    d = Path(folder)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"verdict-{rec['session']}.json"
    f.write_bytes(canonical(rec))
    return f


def run_url(rec: dict) -> str | None:
    g = rec.get("github") or {}
    if not (g.get("repository") and str(g.get("run_id") or "").isdigit()):
        return None
    return f"https://github.com/{g['repository']}/actions/runs/{g['run_id']}" + (f"/attempts/{g['run_attempt']}" if str(g.get("run_attempt") or "").isdigit() else "")


def check_verdict(text: str | bytes, session: dict) -> tuple[dict, str]:
    """(the verdict, its sha256) when it is a code-referee verdict for exactly this session's digest; else AttestError."""
    raw = text.encode() if isinstance(text, str) else bytes(text)
    if len(raw) > MAX_VERDICT:
        raise AttestError("the verdict is too large")
    try:
        rec = json.loads(raw)
    except ValueError:
        raise AttestError("the verdict is not JSON") from None
    if not isinstance(rec, dict) or canonical(rec) != raw:
        raise AttestError("the verdict is not in canonical form (sorted keys, no spaces)")
    if rec.get("kind") != KIND or rec.get("v") != V or rec.get("verdict") != "PASS":
        raise AttestError("not a code-referee PASS verdict")
    if rec.get("session") != session.get("id") or rec.get("digest") != session.get("digest") or rec.get("group_key") != session.get("group_key"):
        raise AttestError("the verdict is not this session's: another session, digest or group")
    g = rec.get("github") or {}
    if g.get("repository") != REPOSITORY or g.get("workflow_ref") != f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main":
        raise AttestError("the verdict was not written by referee.yml on main of " + REPOSITORY)
    if not (isinstance(g.get("sha"), str) and len(g["sha"]) == 40 and str(g.get("run_id") or "").isdigit()):
        raise AttestError("the verdict does not name its commit and run")
    return rec, sha256_hex(raw)


def check_claims(claims: dict, rec: dict, sha: str) -> None:
    """The token (already verified by ghoidc.verify with audience AUD_PREFIX + sha) is the run the verdict names."""
    g = rec["github"]
    if claims.get("aud") != AUD_PREFIX + sha:
        raise AttestError("the token's audience does not name this verdict")
    if claims.get("sha") != g["sha"] or str(claims.get("run_id")) != g["run_id"]:
        raise AttestError("the token is from another commit or run than the verdict says")


# -- Sigstore -----------------------------------------------------------------------------------------------------------
def unsnappy(b: bytes) -> bytes:
    """Snappy block-format decompression (GitHub stores attestation bundles as `*.json.sn`), standard library only."""
    i = n = shift = 0
    while True:
        if i >= len(b) or shift > 35:
            raise AttestError("snappy: bad length")
        c = b[i]; i += 1
        n |= (c & 0x7F) << shift; shift += 7
        if c < 0x80:
            break
    if n > 4 * MAX_BUNDLE:
        raise AttestError("snappy: the bundle is too large")
    out = bytearray()
    while i < len(b):
        tag = b[i]; i += 1
        t = tag & 3
        if t == 0:
            ln = tag >> 2
            if ln >= 60:
                k = ln - 59
                ln = int.from_bytes(b[i:i + k], "little"); i += k
            ln += 1
            if i + ln > len(b):
                raise AttestError("snappy: truncated literal")
            out += b[i:i + ln]; i += ln
            continue
        if t == 1:
            ln, off = ((tag >> 2) & 7) + 4, ((tag >> 5) << 8) | b[i]; i += 1
        elif t == 2:
            ln, off = (tag >> 2) + 1, int.from_bytes(b[i:i + 2], "little"); i += 2
        else:
            ln, off = (tag >> 2) + 1, int.from_bytes(b[i:i + 4], "little"); i += 4
        if off == 0 or off > len(out):
            raise AttestError("snappy: bad copy offset")
        s = len(out) - off
        for j in range(ln):
            out.append(out[s + j])
        if len(out) > n:
            raise AttestError("snappy: longer than it says")
    if len(out) != n:
        raise AttestError("snappy: shorter than it says")
    return bytes(out)


def fetch_bundles(sha: str, repo: str = REPOSITORY, opener=None, token: str | None = None) -> list[bytes]:
    """The attestation bundles GitHub stores for this sha256 in `repo` (public repository: no token needed)."""
    op = opener or urllib.request.urlopen
    hdr = {"Accept": "application/vnd.github+json", "User-Agent": "knos-code-referee"}
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    try:
        with op(urllib.request.Request(f"{API}/repos/{repo}/attestations/sha256:{sha}", headers=hdr), timeout=15) as r:  # noqa: S310
            items = json.loads(r.read()).get("attestations", [])
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise AttestError(f"GitHub's attestation API answered HTTP {e.code}") from None
    out = []
    for a in items:
        if a.get("bundle"):
            out.append(json.dumps(a["bundle"]).encode())
        elif str(a.get("bundle_url", "")).startswith("https://"):
            with op(urllib.request.Request(a["bundle_url"], headers={"User-Agent": "knos-code-referee"}), timeout=15) as r:  # noqa: S310
                raw = r.read(MAX_BUNDLE + 1)
            out.append(unsnappy(raw) if not raw.lstrip().startswith(b"{") else raw)
    return out


def verify_bundle(bundle: bytes | str | dict, sha: str, *, identity: str = IDENTITY, commit: str | None = None,
                  offline: bool = False) -> dict:
    """A Sigstore bundle (actions/attest-build-provenance) for the artifact `sha`, or AttestError. Checked by Knos's own
    Sigstore adapter (knos.sources.sigstore: standard library only, Sigstore's trusted root pinned by sha256): Fulcio
    issued the certificate, Rekor logged it (signed promise and inclusion proof), the DSSE statement is signed by it, and
    it is SLSA v1 provenance. Then here: the certificate's identity is `identity`, issued by GitHub Actions, at `commit`
    when given, and the statement's subjects include `sha`. A bundle in a log that adapter cannot read (a newer Rekor)
    is checked with sigstore-python when it is installed (online trust root; offline: the one it ships).
    Returns {"ok": True, "identity", "commit", "invocation", "log_index", "integrated_time", "checked_by"}."""
    raw = json.dumps(bundle) if isinstance(bundle, dict) else (bundle.decode() if isinstance(bundle, bytes) else bundle)
    if len(raw) > MAX_BUNDLE:
        raise AttestError("the bundle is too large")
    from ..sources import Refused
    from ..sources.sigstore import Sigstore
    try:
        ev = Sigstore().verify(raw.encode())
    except Refused as why:
        if "a log this adapter cannot check" not in str(why):
            raise AttestError(f"the attestation does not verify: {str(why)[:200]}") from None
        return _verify_with_sigstore_python(raw, sha, identity=identity, commit=commit, offline=offline)
    if ev.issuer != ISSUER or ev.signer != identity:
        raise AttestError(f"the attestation does not verify: signed by {ev.signer}, not {identity}")
    if commit and ev.commit != commit:
        raise AttestError("the attestation does not verify: it names another commit")
    if not any(alg == "sha256" and d == sha for _name, alg, d in ev.subjects):
        raise AttestError("the attestation's subjects do not include this verdict")
    index = int(ev.log.rsplit("#", 1)[1]) if "#" in ev.log else None
    return {"ok": True, "identity": ev.signer, "commit": ev.commit, "invocation": ev.run, "log_index": index,
            "integrated_time": ev.signed_at, "checked_by": "knos.sources.sigstore"}


def _verify_with_sigstore_python(raw: str, sha: str, *, identity: str, commit: str | None, offline: bool) -> dict:
    try:
        from sigstore.models import Bundle
        from sigstore.verify import Verifier, policy
    except ImportError:
        raise AttestError("the bundle is in a Rekor log knos.sources.sigstore cannot read, and sigstore-python is not installed") from None
    try:
        b = Bundle.from_json(raw)
        rules = [policy.Identity(identity=identity, issuer=ISSUER)]
        if commit:
            rules.append(policy.GitHubWorkflowSHA(commit))
        ptype, payload = Verifier.production(offline=offline).verify_dsse(b, policy.AllOf(rules))
    except Exception as why:  # noqa: BLE001 - every refusal of sigstore's is a refusal here
        raise AttestError(f"the attestation does not verify: {str(why)[:200]}") from None
    st = json.loads(payload)
    if ptype != IN_TOTO or st.get("predicateType") != SLSA_V1:
        raise AttestError("the attestation is not SLSA v1 provenance")
    if not any((s.get("digest") or {}).get("sha256") == sha for s in st.get("subject", [])):
        raise AttestError("the attestation's subjects do not include this verdict")
    pred = st.get("predicate") or {}
    deps = (pred.get("buildDefinition") or {}).get("resolvedDependencies") or [{}]
    got = (deps[0].get("digest") or {}).get("gitCommit")
    tlog = ((json.loads(raw).get("verificationMaterial") or {}).get("tlogEntries") or [{}])[0]    # the Rekor entry sigstore just checked
    num = lambda v: int(v) if str(v or "").isdigit() else None  # noqa: E731
    return {"ok": True, "identity": identity, "commit": got, "invocation": ((pred.get("runDetails") or {}).get("metadata") or {}).get("invocationId"),
            "log_index": num(tlog.get("logIndex")), "integrated_time": num(tlog.get("integratedTime")), "checked_by": "sigstore-python"}


def rekor_url(log_index) -> str | None:
    return f"https://search.sigstore.dev/?logIndex={int(log_index)}" if isinstance(log_index, int) else None


# -- the attest job's post (standard library only) ----------------------------------------------------------------------
def post_all(folder: str | Path, coordinator: str, *, bundle_path: str | None = None, attestation_url: str | None = None,
             token=None, opener=None) -> list[dict]:
    """POST every verdict in `folder` to the app server with a fresh OIDC token whose audience names that verdict."""
    from .ghoidc import request_token
    tok = token or request_token
    base = coordinator.rstrip("/")
    if not (base.startswith("https://") or base.startswith(("http://127.0.0.1", "http://localhost"))):
        raise AttestError("the coordinator is reached over https")
    bundle = None
    if bundle_path and Path(bundle_path).is_file():
        bundle = Path(bundle_path).read_text(encoding="utf-8")
    out = []
    for f in sorted(Path(folder).glob("verdict-*.json")):
        raw = f.read_bytes()
        rec = json.loads(raw)
        body = {"session": rec["session"], "verdict": raw.decode(), "oidc": tok(audience(raw)), "bundle": bundle,
                "attestation_url": attestation_url}
        req = urllib.request.Request(base + "/api/referee/attest", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "knos-code-referee"})
        try:
            with (opener or urllib.request.urlopen)(req, timeout=180) as r:  # noqa: S310 - https (checked above)
                got = json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                got = {"error": json.loads(e.read()).get("error"), "status": e.code}
            except ValueError:
                got = {"error": f"HTTP {e.code}", "status": e.code}
        out.append({"session": rec["session"], "verdict_sha256": sha256_hex(raw), **{k: got.get(k) for k in ("error", "status", "onchain", "attestation")}})
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m knos.threshold.codeattest")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("post", help="the attest job: post each verdict with its OIDC token to the app server")
    p.add_argument("--dir", required=True)
    p.add_argument("--coordinator", default=os.environ.get("KNOS_REFEREE_COORDINATOR", "https://knos.onrender.com"))
    p.add_argument("--bundle", default="")
    p.add_argument("--attestation-url", default="")
    v = sub.add_parser("verify", help="verify a verdict file's Sigstore attestation (GitHub's API, Sigstore's trust root)")
    v.add_argument("file")
    v.add_argument("--repo", default=REPOSITORY)
    a = ap.parse_args(argv)
    if a.cmd == "post":
        res = post_all(a.dir, a.coordinator, bundle_path=a.bundle or None, attestation_url=a.attestation_url or None)
        print(json.dumps(res, indent=1))
        return 1 if any(r.get("error") for r in res) else 0
    raw = Path(a.file).read_bytes()
    sha, rec = sha256_hex(raw), json.loads(raw)
    for b in fetch_bundles(sha, a.repo):
        try:
            print(json.dumps(verify_bundle(b, sha, commit=(rec.get("github") or {}).get("sha")), indent=1))
            return 0
        except AttestError as why:
            print(f"not this bundle: {why}", file=sys.stderr)
    print(f"no attestation of sha256:{sha} verifies", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
