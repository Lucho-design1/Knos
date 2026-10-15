"""Acceptance check for this issue: mid(a, b, c) in calc.py gives the median of three numbers.

Black-box: the pull request's code runs only as a separate process, through $KNOS_RUN, and only what it prints is
compared with a reference computed here. Most inputs are generated afresh on every run, so no fixed example can be
special-cased.
"""
import json
import os
import random
import subprocess
import sys

rng = random.Random()
cases = [[1, 2, 3], [3, 2, 1], [2, 2, 1], [5, 5, 5], [-1, 0, 1], [0, -7, 7]]
cases += [[rng.randint(-1000, 1000) for _ in range(3)] for _ in range(60)]

program = ("import json, sys\nfrom calc import mid\n"
           "print(json.dumps([mid(*c) for c in json.loads(sys.argv[1])]))")
run = subprocess.run([os.environ["KNOS_RUN"], sys.executable, "-c", program, json.dumps(cases)],
                     capture_output=True, text=True, timeout=120)
try:
    got = json.loads(run.stdout.strip().splitlines()[-1])
except (IndexError, ValueError):
    print("the pull request's code printed no answer:", (run.stdout + run.stderr)[-500:])
    sys.exit(1)
wrong = [(c, g, sorted(c)[1]) for c, g in zip(cases, got) if g != sorted(c)[1]]
if len(got) != len(cases) or wrong:
    for c, g, want in wrong[:5]:
        print(f"mid{tuple(c)} gave {g!r}, expected {want!r}")
    sys.exit(1)
print(f"{len(cases)} triples, all as expected")
