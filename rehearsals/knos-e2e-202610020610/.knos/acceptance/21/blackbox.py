"""Acceptance check for this issue: sign(x) in calc.py gives 1, 0 or -1 as an integer x is positive, zero or negative.

Black-box: the pull request's code runs only as a separate process, through $KNOS_RUN, and only what it prints is
compared with a reference computed here. Most inputs are generated afresh on every run.
"""
import json
import os
import random
import subprocess
import sys

rng = random.Random()
cases = [0, 1, -1, 10**18, -(10**18)]
cases += [rng.randint(-10**12, 10**12) for _ in range(60)]


def reference(c):
    return (c > 0) - (c < 0)


program = ("import json, sys\nfrom calc import sign\n"
           "out = []\n"
           "for c in json.loads(sys.argv[1]):\n"
           "    try:\n"
           "        out.append(sign(c))\n"
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
        print(f"sign({c}) gave {g!r}, expected {want!r}")
    sys.exit(1)
print(f"{len(cases)} cases, all as expected")
