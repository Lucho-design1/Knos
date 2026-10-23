#!/usr/bin/env bash
# Check a champion run's proofs without Knos: the results file, its Sigstore bundle, GitHub's identity for the run,
# and Sigstore's public Rekor v2 log. Needs the GitHub CLI (signed in, to download the artifact) and uv.
#
#   scripts/verify_proofs.sh <run id> [dir]
#   scripts/verify_proofs.sh --files proofs.json proofs.sigstore.json <commit sha>
set -euo pipefail
repo=drexthealpha/Knos
if [ "${1:-}" = --files ]; then
  file=$2 bundle=$3 sha=$4
else
  run=${1:?usage: verify_proofs.sh <run id> [dir]}
  dir=${2:-proofs-$run}
  gh run download "$run" -R "$repo" -n proofs -D "$dir"
  file=$dir/proofs.json bundle=$dir/proofs.sigstore.json
  sha=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["sha"])' "$file")
fi
uvx --from sigstore==4.5.0 sigstore verify github --bundle "$bundle" --repository "$repo" --sha "$sha" \
  --cert-identity "https://github.com/$repo/.github/workflows/champion.yml@refs/heads/main" "$file"
python3 -c 'import json,sys;e=json.load(open(sys.argv[1]))["verificationMaterial"]["tlogEntries"][0];r=json.load(open(sys.argv[2]))
print("rekor", e["kindVersion"]["kind"], e["kindVersion"]["version"], "log index", e["logIndex"]); print(json.dumps(r["results"], indent=1))' "$bundle" "$file"
