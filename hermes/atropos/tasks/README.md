# Synthetic sealed tasks (demo data)

Two synthetic tasks for the Knos Atropos environment and the GEPA judge. They are labelled synthetic in their
task.json and are not drawn from any real repository. Each task folder holds `task.json` (the prompt the policy
sees, the issue number, the fallback `check`) and `base/` (the repository as the work starts). The hidden acceptance
bundle is `base/.knos/acceptance/<issue>/`: the judge runs it; the policy is never shown it.
