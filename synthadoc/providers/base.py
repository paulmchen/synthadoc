# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Paul Chen / axoviq.com
# Plugin interface — third-party providers may extend these base classes under any licence.
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class Message:
    role: str
    content: Union[str, list]  # list for vision: [{"type": "image", ...}, {"type": "text", ...}]


@dataclass
class CompletionResponse:
    text: str
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMProvider(ABC):
    supports_vision: bool = True  # override to False for text-only providers

    @abstractmethod
    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse: ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("embedding not supported by this provider")
