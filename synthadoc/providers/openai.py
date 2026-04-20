# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
from typing import Optional
from openai import AsyncOpenAI
from synthadoc.config import AgentConfig
from synthadoc.providers.base import CompletionResponse, LLMProvider, Message


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
        return CompletionResponse(text=choice.message.content or "",
                                  input_tokens=resp.usage.prompt_tokens,
                                  output_tokens=resp.usage.completion_tokens)
