# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import asyncio
import logging
import re
from typing import Optional
import openai as _openai
from openai import AsyncOpenAI
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

logger = logging.getLogger(__name__)

# Providers whose chat endpoint does not support image inputs
_NO_VISION_HOSTS = ("groq.com", "api.deepseek.com")

# Retry delays (seconds) after an HTTP 429 rate-limit response.
#
# One retry after 65 s covers the most common cause: a per-minute quota window
# that resets after 60 s (the extra 5 s is buffer).  If the second attempt
# also fails, the provider's hourly or daily quota is exhausted — no number of
# additional retries will help.  Failing fast lets the orchestrator requeue the
# job and move on; the worker-level pause (also ~60 s) provides the inter-job
# breathing room.
#
# NOTE: daily quota exhaustion is detected separately (_is_daily_quota_error) and
# raises immediately without any sleep — sleeping 65 s then retrying would waste
# time and burn one more precious daily request on a call that will always fail.
#
# Default demo model is Gemini 2.5 Flash-Lite: 30 RPM / 1,000 RPD.  Groq has similar caps.
_RATE_LIMIT_RETRY_DELAYS_S: tuple[int, ...] = (65,)

# Module-level alias so tests can patch precisely:
#   patch("synthadoc.providers.openai._sleep", new=AsyncMock())
_sleep = asyncio.sleep


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, config: AgentConfig, timeout: int = 0) -> None:
        kwargs: dict = {"api_key": api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**kwargs)
        self._config = config
        self._timeout: int | None = timeout if timeout > 0 else None
        base = str(config.base_url or "")
        self.supports_vision = not any(host in base for host in _NO_VISION_HOSTS)

    @staticmethod
    def _to_openai_content(content):
        """Convert Anthropic-format content blocks to OpenAI format when needed."""
        if not isinstance(content, list):
            return content
        result = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                src = block.get("source", {})
                if src.get("type") == "base64":
                    mime = src.get("media_type", "image/png")
                    data = src.get("data", "")
                    result.append({"type": "image_url",
                                   "image_url": {"url": f"data:{mime};base64,{data}"}})
                    continue
            result.append(block)
        return result

    @staticmethod
    def _is_daily_quota_error(exc: _openai.RateLimitError) -> bool:
        """Return True when this 429 is a per-day (not per-minute) quota exhaustion.

        Gemini's daily-quota response includes a QuotaFailure detail with a
        quotaId containing 'PerDay'.  For Groq, OpenAI, and other providers
        the body won't match and we return False, preserving the 65 s retry.
        """
        body = exc.body if isinstance(exc.body, dict) else {}
        for detail in body.get("error", {}).get("details", []):
            for violation in detail.get("violations", []):
                if "PerDay" in violation.get("quotaId", ""):
                    return True
        text = str(exc).lower()
        return "perday" in text or "requests_per_day" in text or "daily quota" in text

    async def _call_with_retry(self, msgs: list, temperature: float,
                               max_tokens: int):
        """Call the completions API, retrying once on per-minute 429 rate-limit.

        Daily quota exhaustion raises immediately (no sleep, no retry) — sleeping
        65 s and retrying would waste time and consume another scarce daily request.
        See _RATE_LIMIT_RETRY_DELAYS_S for per-minute retry rationale.
        """
        last_exc: Exception | None = None
        for attempt, wait in enumerate([0] + list(_RATE_LIMIT_RETRY_DELAYS_S)):
            if wait:
                logger.warning(
                    "Rate limit (429) from %s — waiting %d s then retrying once "
                    "(per-minute window reset). If this retry also fails, the "
                    "hourly/daily quota is likely exhausted — check your provider "
                    "dashboard or switch providers.",
                    self._config.provider, wait,
                )
                await _sleep(wait)
            try:
                return await self._client.chat.completions.create(
                    model=self._config.model, messages=msgs,
                    temperature=temperature, max_tokens=max_tokens,
                    timeout=self._timeout,
                )
            except _openai.APITimeoutError:
                logger.error(
                    "LLM call to %s timed out after %d s. "
                    "Increase [agents] llm_timeout_seconds in .synthadoc/config.toml "
                    "or switch to a faster model.",
                    self._config.provider, self._timeout,
                )
                raise
            except _openai.RateLimitError as exc:
                if self._is_daily_quota_error(exc):
                    logger.error(
                        "Daily quota exhausted for %s — no retry possible until "
                        "quota resets (typically midnight UTC). Free-tier providers "
                        "cap daily usage; upgrade to a paid API key or switch "
                        "providers.",
                        self._config.provider,
                    )
                    from synthadoc.errors import DailyQuotaExhaustedException
                    raise DailyQuotaExhaustedException(self._config.provider) from exc
                last_exc = exc
        raise last_exc  # type: ignore[misc]

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": self._to_openai_content(m.content)}
                    for m in messages)
        resp = await self._call_with_retry(msgs, temperature, max_tokens)
        if not resp.choices:
            # Some providers (e.g. MiniMax) return choices=null when the model
            # exceeds its internal generation budget. Extract any error details.
            extra = getattr(resp, "model_extra", None) or {}
            base_resp = extra.get("base_resp") or {}
            err_code = base_resp.get("status_code", "unknown")
            err_msg  = base_resp.get("status_msg",  "no details")
            logger.error(
                "OpenAI provider: %s returned choices=null (code=%s, msg=%r). "
                "The model likely timed out internally. Set "
                "[agents] llm_timeout_seconds in .synthadoc/config.toml "
                "(e.g. llm_timeout_seconds = 90) to fail fast, or switch to "
                "a lighter model.",
                self._config.provider, err_code, err_msg,
            )
            raise RuntimeError(
                f"{self._config.provider} returned choices=null "
                f"(code={err_code}): {err_msg}"
            )
        choice = resp.choices[0]
        text = choice.message.content or ""
        # Strip <think>...</think> blocks that reasoning models prepend to their output
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if not text:
            # Reasoning models (e.g. MiniMax M2.x) return content=null and put their
            # answer in a non-standard reasoning_content field.  For structured callers
            # (e.g. decompose) we extract the last JSON array; for prose callers
            # (e.g. query synthesis) we fall back to the full cleaned text.
            extra = getattr(choice.message, "model_extra", None) or {}
            reasoning = (extra.get("reasoning_content") or "").strip()
            if reasoning:
                clean = re.sub(r"<think>.*?</think>", "", reasoning, flags=re.DOTALL).strip()
                last_close = clean.rfind("]")
                if last_close >= 0:
                    last_open = clean.rfind("[", 0, last_close)
                    if last_open >= 0:
                        text = clean[last_open: last_close + 1]
                        logger.debug(
                            "OpenAI provider: content=null — extracted JSON from reasoning_content"
                        )
                if not text:
                    text = clean
                    logger.debug(
                        "OpenAI provider: content=null — using full reasoning_content as prose answer"
                    )
        return CompletionResponse(text=text,
                                  input_tokens=resp.usage.prompt_tokens,
                                  output_tokens=resp.usage.completion_tokens)
