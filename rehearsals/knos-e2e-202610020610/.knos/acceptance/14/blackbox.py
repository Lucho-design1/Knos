"""Acceptance check for this issue: digitsum(n) in calc.py gives the sum of the decimal digits of any integer.

Black-box: the pull request's code runs only as a separate process, through $KNOS_RUN, and only what it prints is
compared with a reference computed here. Most inputs are generated afresh on every run, and they include negative
integers, which the issue names.
"""
import json
import os
import random
import subprocess
import sys

rng = random.Random()
cases = [0, 7, 12, 909, -12, -1]
cases += [rng.randint(-10**12, 10**12) for _ in range(60)]


def reference(n: int) -> int:
    return sum(int(d) for d in str(abs(n)))


program = ("import json, sys\nfrom calc import digitsum\n"
           "out = []\n"
           "for n in json.loads(sys.argv[1]):\n"
           "    try:\n"
           "        out.append(digitsum(n))\n"
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
wrong = [(n, g, reference(n)) for n, g in zip(cases, got) if g != reference(n)]
if len(got) != len(cases) or wrong:
    for n, g, want in wrong[:5]:
        print(f"digitsum({n}) gave {g!r}, expected {want!r}")
    sys.exit(1)
print(f"{len(cases)} integers, all as expected")
