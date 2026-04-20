# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import asyncio
from typing import Optional
import anthropic as anthropic_lib
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

# RateLimitError (429) is not retried — quota exhaustion needs a provider switch or wait.
# InternalServerError covers transient 500/529 overload; retry with backoff.
_RETRYABLE = (anthropic_lib.InternalServerError,)
_RATE_LIMIT = (anthropic_lib.RateLimitError,)
_MAX_RETRIES = 3


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, config: AgentConfig) -> None:
        self._client = anthropic_lib.AsyncAnthropic(api_key=api_key)
        self._config = config

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        kwargs: dict = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if system:
            kwargs["system"] = system
        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.messages.create(**kwargs)
                text = "".join(b.text for b in resp.content if hasattr(b, "text"))
                return CompletionResponse(text=text,
                                         input_tokens=resp.usage.input_tokens,
                                         output_tokens=resp.usage.output_tokens)
            except _RATE_LIMIT:
                raise  # quota exhaustion — propagate immediately, no retry
            except _RETRYABLE as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)  # 0 s, 1 s, 2 s backoff
                continue
            except Exception:
                raise
        raise last_exc
