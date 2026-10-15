# knos-e2e-202610020610
Knos 0.3.9 release E2E

Knos 0.3.15 rehearsal (neutral re-execution): `.github/workflows/knos.yml` calls the workflows at commit
`202c70754fdfee52dd2f00c614867b0a490c78e5`, which is drexthealpha/knos-workflows-rc@202c70754fdfee52dd2f00c614867b0a490c78e5 (the 0.3.15 tree's workflows built on the staging programs),
pushed here unchanged as the branch `knos-workflows-rc` so that a public repository can call them. Devnet, test money.

Knos 0.3.18 staging run on the PUBLIC program ids: `.github/workflows/knos.yml` and `knos-check.yml` call the workflows at
commit `c4a1f19d4d65f74b47ca3148701cece98a9e30e4`, which is drexthealpha/knos-workflows-rc@c4a1f19d4d65f74b47ca3148701cece98a9e30e4 (the 0.3.18 tree's workflows, knos installed from
drexthealpha/knos-rc@023e6ac), pushed here unchanged as the branch `knos-workflows-0318` so that a repository can call
them. Devnet, test money.

Since Knos 0.3.24 (10 Oct 2026) every workflow here calls released code: `knos.yml`, `knos-check.yml`, `knos-attest.yml`
and `knos-meter-batch.yml` call drexthealpha/knos-workflows at `64b31fae2b0050ee6abeeb763442172f42398cd5` (knos 0.3.24
from PyPI, by hash), and `knos-supplier.yml` calls drexthealpha/Knos `supplier.yml` at v0.3.24
(`fb4217c1a22c1556cbfce5bc42258aa409fac300`). Before, they called this repository's own copies at `876f3ced`, which
installed knos from the staging repository. A bounty funded through an earlier commit of the workflows is paid only
through that commit.
