"""One OpenAPI 3.1 document for this server, served at /openapi.json beside the hosted MCP endpoint (/mcp).

Built from the route tables the server dispatches on (server.ROUTES + server.GET_ROUTES + product_routes.ROUTES), so a
route cannot exist without being documented. validate() checks the structure this server relies on; the release
evidence also runs the document through openapi-spec-validator.
"""
from __future__ import annotations

from . import product_routes

TYPES = {"string": {"type": "string"}, "integer": {"type": "integer"}, "array": {"type": "array", "items": {}}, "object": {"type": "object"}, "boolean": {"type": "boolean"}}


def _routes():
    from . import server
    seen = {(m, p) for m, p, *_ in product_routes.ROUTES}
    rows = list(product_routes.ROUTES)
    for p in server.ROUTES:
        if ("POST", p) not in seen:
            rows.append(("POST", p, p in server.SIGNED_IN, server.SUMMARIES.get(p, f"POST {p}"), {}))
    for p, summary in server.GET_ROUTES.items():
        if ("GET", p) not in seen:
            rows.append(("GET", p, False, summary, {}))
    rows.append(("POST", "/api/pay/fund", False, "Solana Pay transaction request: {account} -> the milestone's funding transaction to sign",
                 {"project": "string", "milestone": "string", "units": "integer", "account": "string"}))
    rows.append(("POST", "/mcp", False, "Hosted MCP (Streamable HTTP, JSON-RPC 2.0): Knos's tools for agents", {}))
    return rows


def document(base: str = "https://knos.onrender.com") -> dict:
    paths: dict = {}
    for method, path, signed, summary, fields in _routes():
        op = {"summary": summary, "operationId": (method.lower() + path.replace("/", "_").replace("{", "").replace("}", "")).strip("_"),
              "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object"}}}},
                            "400": {"description": "refused, with the reason in `error`"},
                            "429": {"description": "rate limited"}}}
        if signed:
            op["security"] = [{"session": []}]
            op["responses"]["401"] = {"description": "sign in first"}
        params = [{"name": n, "in": "path", "required": True, "schema": {"type": "string"}} for n in _path_params(path)]
        if method == "GET":
            params += [{"name": k, "in": "query", "required": False, "schema": TYPES.get(t, {"type": "string"})} for k, t in fields.items()]
        elif fields:
            op["requestBody"] = {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "properties": {k: TYPES.get(t, {"type": "string"}) for k, t in fields.items()}}}}}
        if method == "POST" and path in DEMAND_BODIES:      # the demand check: every Qloo family field, typed, with an example
            op["requestBody"] = {"required": True, "content": {"application/json": {"schema": demand_body(path),
                                 "examples": {"who-and-where": {"summary": "Who and where",
                                              "value": {"idea": "trail running shoes for ultramarathons", "age": "24_and_younger", "near": "Austin", "radius": 5000}},
                                              "price-and-brand": {"summary": "Price tier and who serves it",
                                              "value": {"idea": "a cold brew coffee shop", "near": "Seattle", "price_level": "1", "references_brand": "Starbucks"}}}}}}
        if params:
            op["parameters"] = params
        paths.setdefault(path, {})[method.lower()] = op
    return {"openapi": "3.1.0",
            "info": {"title": "Knos", "version": _version(),
                     "description": "Knos carries research across the valley of death: each step is paid only on verified proof. Demand checks on Qloo, Ready briefs, milestone "
                                    "money held on Solana until the proof passes; devnet, test money, no customers yet. Agents: the same tools over MCP at /mcp."},
            "servers": [{"url": base}],
            "components": {"securitySchemes": {"session": {"type": "http", "scheme": "bearer",
                                                           "description": "the session token a sign-in returns (passkey, SSO, Google, ORCID, email, guest)"}}},
            "paths": dict(sorted(paths.items()))}


DEMAND_BODIES = {"/api/check": "idea", "/api/cross": "ref or idea"}


def demand_body(path: str) -> dict:
    """The body of a demand check: the idea (or paper), the market, and every family field of knos.qloo_families."""
    from knos import qloo_families as Q
    props = {"idea": {"type": "string", "description": "the product idea, 8 to 500 characters", "examples": ["a cold brew coffee shop"]},
             "place": {"type": "string", "description": "the launch market (city or country)", "examples": ["Austin"]},
             "leader": {"type": "string", "description": "the market leader to compare against", "examples": ["Starbucks"]}}
    if path == "/api/cross":
        props = {"ref": {"type": "string", "description": "a paper id (DOI, arXiv, PubMed, OpenAlex, patent)", "examples": ["10.1038/nature16521"]},
                 **props, "product": {"type": "string", "description": "the product phrase"}}
    props.update({k: Q.schema(k) for k in Q.FIELDS})
    return {"type": "object", "properties": props, **({"required": ["idea"]} if path == "/api/check" else {}), "additionalProperties": False}


def _path_params(path: str) -> list[str]:
    import re
    return re.findall(r"{([a-z_]+)}", path)


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("knos")
    except Exception:  # noqa: BLE001
        return "0.4.0"


def validate(doc: dict) -> list[str]:
    errs = []
    if doc.get("openapi") != "3.1.0" or not doc.get("info", {}).get("title") or not doc.get("info", {}).get("version"):
        errs.append("openapi/info")
    ids = set()
    for path, ops in doc.get("paths", {}).items():
        if not path.startswith("/"):
            errs.append(f"{path}: must start with /")
        for m, op in ops.items():
            if m not in ("get", "post", "put", "delete", "patch", "options"):
                errs.append(f"{path} {m}: method")
            if op["operationId"] in ids:
                errs.append(f"{path} {m}: duplicate operationId")
            ids.add(op["operationId"])
            if not op.get("responses"):
                errs.append(f"{path} {m}: responses")
            for prm in op.get("parameters", []):
                if prm["in"] == "path" and "{" + prm["name"] + "}" not in path:
                    errs.append(f"{path}: path parameter {prm['name']}")
            for s in op.get("security", []):
                for k in s:
                    if k not in doc["components"]["securitySchemes"]:
                        errs.append(f"{path}: security {k}")
    return errs
