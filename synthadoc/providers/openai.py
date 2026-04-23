# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import logging
import re
from typing import Optional
from openai import AsyncOpenAI
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

logger = logging.getLogger(__name__)

# Providers whose chat endpoint does not support image inputs
_NO_VISION_HOSTS = ("groq.com",)


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, config: AgentConfig) -> None:
        kwargs: dict = {"api_key": api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = AsyncOpenAI(**kwargs)
        self._config = config
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

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend({"role": m.role, "content": self._to_openai_content(m.content)}
                    for m in messages)
        resp = await self._client.chat.completions.create(
            model=self._config.model, messages=msgs,
            temperature=temperature, max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        text = choice.message.content or ""
        # Strip <think>...</think> blocks that reasoning models prepend to their output
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if not text:
            # Reasoning models (e.g. MiniMax M2.x) return content=null and put their
            # chain-of-thought in a non-standard reasoning_content field. Try to extract
            # the last JSON-like block from it so structured callers still get a result.
            extra = getattr(choice.message, "model_extra", None) or {}
            reasoning = (extra.get("reasoning_content") or "").strip()
            if reasoning:
                last_close = reasoning.rfind("]")
                if last_close >= 0:
                    last_open = reasoning.rfind("[", 0, last_close)
                    if last_open >= 0:
                        text = reasoning[last_open: last_close + 1]
                        logger.debug(
                            "OpenAI provider: content=null — extracted JSON from reasoning_content"
                        )
        return CompletionResponse(text=text,
                                  input_tokens=resp.usage.prompt_tokens,
                                  output_tokens=resp.usage.completion_tokens)
