#!/usr/bin/env bash
# Re-make the evidence in this folder. Usage: run.sh KNOS_CHECKOUT_AT_99cc4e3e PATH_TO_A_KNOS_e2e_CLONE OUT
# 1. knos reproduce on the Knos checkout with the spec here (the spec names this folder's scripts by absolute path,
#    so its sha256 differs per machine; the claims and their numbers do not).
# 2. knos taskpack export of drexthealpha/knos-e2e#272 (owner's repository; --opt-in given for the demo) and grading
#    of the three candidate patches in this folder.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; knos_repo="$1"; e2e="$2"; out="$3"
sed "s#@DIR@#$here#g" "$here/knos-tasks.yml.in" > "$out.knos-tasks.yml"
knos reproduce "$knos_repo" --spec "$out.knos-tasks.yml" --out "$out/repro"
knos taskpack export drexthealpha/knos-e2e#272 --repo-dir "$e2e" --out "$out/taskpacks" --opt-in --maintainer drexthealpha
pack="$(ls -d "$out"/taskpacks/knos-task-* | head -1)"
for c in reference cheat wrong; do knos taskpack grade "$pack" --patch "$here/cand-$c.patch" --repo-dir "$e2e" > "$out/grade-$c.json" || true; done
knos taskpack rows "$pack" --out "$out/rows.jsonl"
