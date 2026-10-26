"""Every provider fact this package uses, with the page it was read from and the day. Nothing here is guessed: a fact the pages did not give is not used.

Model ids and prices: the Token Factory model catalog, read 14 Oct 2026. The catalog spells the two ids differently
(lower case for Super, mixed case for Ultra); they are copied exactly. `GET /v1/models` on the live API is the check.
"""
from __future__ import annotations

FETCHED = "2026-10-14"

# Nebius Token Factory (OpenAI-compatible)
BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
CHAT_PATH = "chat/completions"                     # POST /v1/chat/completions, HTTP bearer auth
MODELS_PATH = "models"                             # GET /v1/models
KEY_ENV = "NEBIUS_API_KEY"

SUPER = "nvidia/nemotron-3-super-120b-a12b"        # Nemotron 3 Super: the coder (proposals, diffs, rule drafts)
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"        # Nemotron 3 Ultra: the advisory "why this is a cheat" explanation

# USD per 1M tokens (input, output), Token Factory model catalog, us-central1, read 14 Oct 2026
PRICE_PER_M = {SUPER: (0.30, 0.90), ULTRA: (1.00, 3.00)}

# Tavily
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_KEY_ENV = "TAVILY_API_KEY"
TAVILY_CREDITS = {"basic": 1, "advanced": 2}       # credits per search, by search_depth
TAVILY_USD_PER_CREDIT = 0.008                      # pay-as-you-go price per credit

MOCK = "MOCK (synthetic, not a real API response)"

SOURCES = {
    "token_factory_overview": "https://docs.tokenfactory.nebius.com/",
    "chat_completions": "https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion.md",
    "json_output": "https://docs.tokenfactory.nebius.com/ai-models-inference/json.md",
    "list_models": "https://docs.tokenfactory.nebius.com/api-reference/models/list-models.md",
    "model_catalog": "https://tokenfactory.nebius.com/model-catalog.md",
    "super_launch": "https://nebius.com/blog/posts/nemotron3-super-now-available",
    "serverless_jobs": "https://docs.nebius.com/serverless/quickstart/jobs",
    "serverless_jobs_manage": "https://docs.nebius.com/serverless/jobs/manage",
    "serverless_endpoints": "https://docs.nebius.com/serverless/quickstart/endpoints",
    "tavily_search": "https://docs.tavily.com/documentation/api-reference/endpoint/search",
    "tavily_credits": "https://docs.tavily.com/documentation/api-credits",
}


def token_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD for one call at the catalog price; 0.0 for a model with no published price here."""
    p_in, p_out = PRICE_PER_M.get(model, (0.0, 0.0))
    return (prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000
