import argparse, os
ap = argparse.ArgumentParser(); ap.add_argument("--seed", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); open(os.path.join(a.out, "seed.txt"), "w").write(str(a.seed))
