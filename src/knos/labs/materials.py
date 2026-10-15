"""Materials Project: COMPUTATIONAL ground truth for materials claims (DFT-computed properties), not a lab.

A claimed new material is checked against what the Materials Project has computed before anyone pays for synthesis:
"is it on or near the convex hull?", "is its band gap what the claim says?". Nothing is bought: the "order" is a
query, and the results are the documents the API returned, hashed.

Read 14 Oct 2026 (sources in docs/reference/LABS.md):
  base     https://api.materialsproject.org
  auth     X-API-KEY header (OpenAPI securitySchemes.ApiKeyAuth, api.materialsproject.org/openapi.json). A key is
           REQUIRED: an unauthenticated GET /materials/summary/ answered 401 {"message": "No API key found in request"}.
           The key is on next-gen.materialsproject.org/dashboard after signing in (GitHub, Google, Facebook, Microsoft,
           Amazon or an email link; docs.materialsproject.org). Knos reads it from $MP_API_KEY (the variable the
           official mp-api client reads) and never prints it.
  query    GET /materials/summary/?material_ids=mp-149&_fields=...&license=BY-C -> {"data": [SummaryDoc], "errors", "meta"}
           fields: material_id, formula_pretty, energy_above_hull (eV/atom), formation_energy_per_atom (eV/atom),
           band_gap (eV), is_stable, density (g/cm3), volume, symmetry, builder_meta.license ("BY-C" | "BY-NC")
  limits   "rate limits on requests starting at 25/second" (docs: tips for large downloads)
  licence  per document: BY-C (CC BY, commercial use allowed) or BY-NC (the GNoME batch, non-commercial). Knos is a
           commercial verification service, so it asks for license=BY-C only and cites the Materials Project.

Fixture mode replays fixtures/materials_project.json: the values for mp-149 (silicon) as the LEGACY Materials Project
site shows them (legacy.materialsproject.org/materials/mp-149), placed in the API's response shape. The current
database may differ; one authenticated call refreshes it.
"""
from __future__ import annotations

import urllib.parse

from .base import Adapter, LabError, Order, Quote, Results, Spec, Status, canonical, sha256_hex

FIELDS = ("material_id", "formula_pretty", "energy_above_hull", "formation_energy_per_atom", "band_gap", "is_stable",
          "density", "builder_meta")


class MaterialsProject(Adapter):
    NAME = "materials_project"
    FIELD = "materials"
    KEY_ENV = "MP_API_KEY"
    BASE = "https://api.materialsproject.org"
    DOCS = "https://docs.materialsproject.org/downloading-data/using-the-api/getting-started"
    LIVE_READY = True
    ORDERS = False

    def auth_headers(self) -> dict:
        return {"X-API-KEY": self.key()}

    @staticmethod
    def ids(spec: Spec) -> list[str]:
        got = spec.protocol.get("material_ids")
        if not isinstance(got, list) or not got or not all(isinstance(x, str) and x.startswith("mp-") for x in got):
            raise LabError("protocol.material_ids: a list of Materials Project ids (mp-149, or the new alphabetical mp-...)")
        return got

    def _path(self, spec: Spec) -> str:
        q = {"material_ids": ",".join(self.ids(spec)), "_fields": ",".join(FIELDS), "license": "BY-C"}
        return "/materials/summary/?" + urllib.parse.urlencode(q, safe=",")

    def quote(self, spec: Spec) -> Quote:
        self.ids(spec)
        return Quote(self.NAME, "0.00", "USD", 0, None, None, [{"what": "computed reference data, no purchase"}], [],
                     self.is_fixture, self.label)

    def order(self, spec: Spec, escrow_ref: str, quote: Quote | None = None) -> Order:
        """Nothing is bought: the 'order' is the query, named by its hash."""
        return Order(self.NAME, "mpq-" + sha256_hex(self._path(spec))[:16], escrow_ref, spec.hash(), "submitted", self.is_fixture,
                     self.label, {"query": self._path(spec), "spec": spec.protocol})

    def status(self, order: Order) -> Status:
        return Status(self.NAME, order.order_id, "completed", "query", self.is_fixture, self.label)

    def results(self, order: Order) -> Results:
        path = order.raw.get("query")
        if not path:
            raise LabError("this order carries no query")
        _s, a, _h = self._call("GET", path)
        docs = a.get("data") or []
        runs = []
        for d in docs:
            lic = (d.get("builder_meta") or {}).get("license")
            runs.append({"id": d.get("material_id"), "ok": True, "why": None, "license": lic,
                         "measurements": {k: d.get(k) for k in FIELDS if k not in ("material_id", "builder_meta")}})
        asked = order.raw.get("spec", {}).get("material_ids", [])
        missing = sorted(set(asked) - {r["id"] for r in runs})
        nc = [r["id"] for r in runs if r.get("license") not in ("BY-C", None)]
        why = ([f"not returned: {', '.join(missing)}"] if missing else []) + ([f"not BY-C: {', '.join(nc)}"] if nc else []) + \
              ([f"errors: {a.get('errors')}"] if a.get("errors") else [])
        qc = {"passed": not why, "why": "; ".join(why) or None, "documents": len(docs), "license": "BY-C",
              "api_version": (a.get("meta") or {}).get("api_version"), "rule": "knos"}
        body_hash = sha256_hex(canonical(a))
        return Results(self.NAME, order.order_id, "completed", runs, qc, [{"name": "summary.json", "sha256": body_hash}],
                       {"material_ids": asked}, self.is_fixture, self.label, a)
