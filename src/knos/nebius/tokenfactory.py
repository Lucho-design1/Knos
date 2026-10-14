"""A small client for Nebius Token Factory's OpenAI-compatible API (chat completions, list models), standard library
only. Live when NEBIUS_API_KEY is set; otherwise MOCK: the reply is made locally by a `responder` and shaped like the
documented response (id, object "chat.completion", choices[].message.content, finish_reason, usage), with the field
`knos_mock` saying so. A mock reply is never presented as a model's output.

The key is read from the environment only, sent only in the Authorization header to BASE_URL, never logged, stored or
put in an error message.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from . import sources

Transport = Callable[[str, str, dict, dict | None, float], dict]    # (method, url, headers, body, timeout) -> json


class TokenFactoryError(RuntimeError):
    pass


@dataclass
class Reply:
    model: str
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    mock: bool
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        return sources.token_cost(self.model, self.prompt_tokens, self.completion_tokens)

    def to_dict(self) -> dict:
        return {"model": self.model, "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                "latency_s": round(self.latency_s, 4), "cost_usd": round(self.cost_usd, 8), "mock": self.mock,
                "finish_reason": self.finish_reason, **({"label": sources.MOCK} if self.mock else {})}


def _http(method: str, url: str, headers: dict, body: dict | None, timeout: float) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:    # noqa: S310 - a fixed https base URL
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as why:
        detail = why.read().decode(errors="replace")[:300]
        raise TokenFactoryError(f"{method} {url}: HTTP {why.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as why:
        raise TokenFactoryError(f"{method} {url}: {type(why).__name__}: {why}") from None


def estimate_tokens(text: str) -> int:
    """MOCK usage only: about four characters per token. Never used for a live reply (the API's usage is)."""
    return max(1, math.ceil(len(text) / 4))


class TokenFactory:
    """`chat(model, messages, ...)` -> Reply. `live` is True only when a key is present (argument or NEBIUS_API_KEY)."""

    def __init__(self, api_key: str | None = None, *, responder: Callable[[str, list[dict]], str] | None = None,
                 transport: Transport | None = None, base_url: str = sources.BASE_URL, timeout_s: float = 180.0):
        self._key = api_key if api_key is not None else os.environ.get(sources.KEY_ENV, "")
        self.live = bool(self._key)
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.timeout_s = timeout_s
        self._transport = transport or _http
        self._responder = responder
        self.calls: list[Reply] = []

    @property
    def mode(self) -> str:
        return "live" if self.live else "mock"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json", "Accept": "application/json"}

    def models(self) -> list[str]:
        """GET /v1/models: the ids the account can call (live only; the check before trusting a hard-coded id)."""
        if not self.live:
            return []
        got = self._transport("GET", self.base_url + sources.MODELS_PATH, self._headers(), None, self.timeout_s)
        return [m.get("id", "") for m in got.get("data", [])]

    def chat(self, model: str, messages: list[dict], *, max_tokens: int = 4096, temperature: float = 0.2,
             response_format: dict | None = None) -> Reply:
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if response_format:
            body["response_format"] = response_format
        t0 = time.perf_counter()
        if self.live:
            raw = self._transport("POST", self.base_url + sources.CHAT_PATH, self._headers(), body, self.timeout_s)
        else:
            if self._responder is None:
                raise TokenFactoryError(f"{sources.KEY_ENV} is not set and no mock responder was given")
            raw = mock_completion(model, messages, self._responder(model, messages))
        latency = time.perf_counter() - t0
        reply = parse_completion(raw, model, latency, mock=not self.live)
        self.calls.append(reply)
        return reply


def mock_completion(model: str, messages: list[dict], content: str) -> dict:
    """A chat.completion object in the documented shape, made locally and labelled MOCK."""
    prompt = "".join(str(m.get("content", "")) for m in messages)
    return {"id": "mock-" + hashlib.sha256((model + prompt + content).encode()).hexdigest()[:24],
            "object": "chat.completion", "created": 0, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": estimate_tokens(prompt), "completion_tokens": estimate_tokens(content),
                      "total_tokens": estimate_tokens(prompt) + estimate_tokens(content)},
            "knos_mock": sources.MOCK}


def parse_completion(raw: dict, model: str, latency_s: float, *, mock: bool) -> Reply:
    try:
        choice = raw["choices"][0]
        text = choice["message"].get("content") or ""
        usage = raw.get("usage") or {}
    except (KeyError, IndexError, TypeError, AttributeError) as why:
        raise TokenFactoryError(f"not a chat.completion response: {type(why).__name__}") from None
    return Reply(model, text, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0),
                 latency_s, mock, choice.get("finish_reason") or "", raw)
