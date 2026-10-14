"""Nemotron 3 Ultra writes the "why this is a cheat" paragraph. ADVISORY ONLY.

The verdict is the referee's (deterministic rules, sealed data). This module copies that verdict into its output
unchanged and adds a paragraph for the person reading it. Whatever the model writes, even "this is fine", the verdict
field does not move: the model sees the verdict, it does not make it.
"""
from __future__ import annotations

import json

from . import sources
from .tokenfactory import TokenFactory

SYSTEM = ("ROLE: cheat explainer. The Knos referee has already refused a change; its decision is final and you cannot "
          "change it. Explain to a maintainer, in at most five plain sentences, why each finding is a way to pass a "
          "check without doing the work, quoting the evidence. Do not suggest how to evade the rule.")


def explain(client: TokenFactory, *, verdict: str, findings: list[dict], subject: str, model: str = sources.ULTRA) -> dict:
    user = json.dumps({"verdict": verdict, "findings": findings, "change": subject[:12_000]}, indent=1)
    reply = client.chat(model, [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                        max_tokens=600, temperature=0.1)
    return {"verdict": verdict, "verdict_source": "Knos referee (deterministic rules)",
            "rules": sorted({str(f.get("rule")) for f in findings}),
            "explanation": reply.text.strip(), "explained_by": model, "advisory": True,
            "mock": reply.mock, **({"label": sources.MOCK} if reply.mock else {})}
