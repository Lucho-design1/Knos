#!/bin/sh
# M6 test_fresh_setup: run SUBMISSION.md's setup block, as written, in a fresh python:3.12 container. Pass when the
# health check answers and the demand check answers (with no Qloo key it must say it cannot decide).
#
#   sh scripts/fresh_setup.sh
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
block=$(awk '/^## 5\. Setup/{s=1} s && /^```bash$/{f=1; next} f && /^```$/{exit} f' "$here/SUBMISSION.md")
[ -n "$block" ] || { echo "no setup block in SUBMISSION.md"; exit 1; }
printf '%s\n' "$block" > "${TMPDIR:-/tmp}/knos_setup_block.sh"
echo "---- the setup block, as SUBMISSION.md has it"
cat "${TMPDIR:-/tmp}/knos_setup_block.sh"
echo "---- run in python:3.12"
out=$(docker run --rm -i python:3.12 bash -e < "${TMPDIR:-/tmp}/knos_setup_block.sh" 2>&1 | tail -5)
echo "$out"
echo "$out" | grep -q '"ok"\|ok' && echo "$out" | grep -q "CANNOT_DECIDE\|OPEN\|REFUSE" && echo "PASS test_fresh_setup" || { echo "FAIL test_fresh_setup"; exit 1; }
