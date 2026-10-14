"""Knos builds Knos on Nemotron: NVIDIA Nemotron 3 models on Nebius Token Factory as Knos's coders and explainer,
Tavily for provenance and new cheat patterns. The models propose and explain; the Knos referee decides.

    tokenfactory   OpenAI-compatible client (live with NEBIUS_API_KEY, else MOCK replies in the documented shape)
    coder          Nemotron 3 Super as a knos.autoresearch proposer and as a knos.self diff writer + check-pr screen
    explain        Nemotron 3 Ultra's advisory "why this is a cheat" paragraph; the verdict is copied, never changed
    tavily         search (live with TAVILY_API_KEY, else MOCK), provenance of submitted code
    rules_intake   a web-found pattern becomes a cheat rule only if it passes the referee's own known-case test
    rerun          Nebius Serverless Job when the operator opts in and the CLI is there, else the local sandbox
    panel, demo    the live panel and the golden path (`python -m knos.nebius demo`)

docs/reference/NEBIUS.md cites every provider fact with the page and the day it was read.
"""
