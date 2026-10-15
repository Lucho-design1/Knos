"""Acceptance check for this issue: clamp(x, lo, hi) in calc.py gives x held between lo and hi (lo <= hi).

Black-box: the pull request's code runs only as a separate process, through $KNOS_RUN, and only what it prints is
compared with a reference computed here. Most inputs are generated afresh on every run.
"""
import json
import os
import random
import subprocess
import sys

rng = random.Random()
cases = [[5, 0, 10], [-3, 0, 10], [42, 0, 10], [0, 0, 0]]
for _ in range(60):
    lo = rng.randint(-1000, 1000)
    cases.append([rng.randint(-5000, 5000), lo, lo + rng.randint(0, 2000)])


def reference(c):
    return min(max(c[0], c[1]), c[2])


program = ("import json, sys\nfrom calc import clamp\n"
           "out = []\n"
           "for c in json.loads(sys.argv[1]):\n"
           "    try:\n"
           "        out.append(clamp(*c))\n"
           "    except Exception as e:\n"
           "        out.append(type(e).__name__)\n"
           "print(json.dumps(out))")
run = subprocess.run([os.environ["KNOS_RUN"], sys.executable, "-c", program, json.dumps(cases)],
                     capture_output=True, text=True, timeout=120)
try:
    got = json.loads(run.stdout.strip().splitlines()[-1])
except (IndexError, ValueError):
    print("the pull request's code printed no answer:", (run.stdout + run.stderr)[-500:])
    sys.exit(1)
wrong = [(c, g, reference(c)) for c, g in zip(cases, got) if g != reference(c)]
if len(got) != len(cases) or wrong:
    for c, g, want in wrong[:5]:
        print(f"clamp({c}) gave {g!r}, expected {want!r}")
    sys.exit(1)
print(f"{len(cases)} cases, all as expected")
