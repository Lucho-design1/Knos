"""Demo entry (REPRO, v0.3.29): run in a copy of the Knos repository. For every playground task in tasks/*, draw the
judge's inputs from gen.py with the seed in {data}/seed.txt and count the wrong solutions whose answers differ from the
reference on at least one input. Writes {"wrong_caught_rate", "reference_ok_rate", "tasks", "wrong"} to --out."""
import argparse, importlib.util, json, random, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--split", default="test"); ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
seed = int((Path(a.data) / "seed.txt").read_text())

def mod(path):
    spec = importlib.util.spec_from_file_location(f"m{abs(hash(str(path)))}", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def answer(m, text):
    try:
        return str(m.solve(text)).strip()
    except Exception as e:  # a crash is an answer that differs
        return f"<error {type(e).__name__}>"

tasks = wrong = caught = ref_ok = 0
for folder in sorted(p for p in Path("tasks").iterdir() if (p / "task.json").is_file()):
    t = json.loads((folder / "task.json").read_text())
    if not t.get("wrong"):
        continue
    tasks += 1
    ref = mod(folder / t["reference"])
    cases = mod(folder / t["hidden"]).inputs(random.Random(seed))
    ref_ok += all(answer(ref, c["input"]) == c["output"] for c in t["public"])
    for w in t["wrong"]:
        wrong += 1
        wm = mod(folder / w)
        caught += any(answer(wm, x) != answer(ref, x) for x in cases)
json.dump({"wrong_caught_rate": caught / wrong, "reference_ok_rate": ref_ok / tasks, "tasks": tasks, "wrong": wrong}, open(a.out, "w"))
