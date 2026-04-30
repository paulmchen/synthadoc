# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import json as _json
import shutil
import sys
from abc import abstractmethod
from typing import Optional

from synthadoc.providers.base import CompletionResponse, LLMProvider, Message


class CodingToolCLIProvider(LLMProvider):
    """Abstract base for coding tool CLI providers (Claude Code, Opencode, …).

    Subclasses implement _build_command, _parse_output, and _is_quota_exhausted.
    The prompt is always passed via stdin to avoid OS argument length limits.
    """
    supports_vision = False
    _tool_binary: str  # e.g. "claude" or "opencode" — set by subclass

    def __init__(self, model: Optional[str], timeout: int) -> None:
        resolved = shutil.which(self._tool_binary)
        if resolved is None:
            raise EnvironmentError(
                f"[ERR-PROV-003] '{self._tool_binary}' not found in PATH. "
                f"Install it and ensure it is authenticated before using this provider."
            )
        # On Windows, .cmd/.bat wrappers cannot be executed directly by
        # create_subprocess_exec — they must be run via "cmd /c".
        self._cmd_prefix: list[str] = (
            ["cmd", "/c"] if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat"))
            else []
        )
        self._model = model
        self._timeout = timeout or None

    @abstractmethod
    def _build_command(self) -> list[str]:
        """Return the subprocess argv list (prompt is passed via stdin, not here)."""

    @abstractmethod
    def _parse_output(self, raw: str) -> CompletionResponse:
        """Parse stdout from the tool into a CompletionResponse. Raise ValueError on bad output."""

    @abstractmethod
    def _is_quota_exhausted(self, stderr: str) -> bool:
        """Return True if stderr indicates the tool's usage quota is exhausted."""

    def _build_prompt(self, messages: list[Message], system: Optional[str]) -> str:
        """Combine system message and user messages into a single prompt string."""
        parts = []
        if system:
            parts.append(system)
        for m in messages:
            content = m.content if isinstance(m.content, str) else str(m.content)
            parts.append(content)
        return "\n\n".join(parts)

    async def complete(self, messages: list[Message], system: Optional[str] = None,
                       temperature: float = 0.0, max_tokens: int = 4096) -> CompletionResponse:
        prompt = self._build_prompt(messages, system)
        cmd = self._cmd_prefix + self._build_command()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(
                f"{self._tool_binary}: LLM call timed out after {self._timeout}s. "
                f"Increase agents.llm_timeout_seconds in config.toml."
            )

        stderr_text = stderr.decode(errors="replace").strip()
        if self._is_quota_exhausted(stderr_text):
            from synthadoc.errors import CodingToolQuotaExhaustedException
            raise CodingToolQuotaExhaustedException(self._tool_binary)

        if proc.returncode != 0:
            raise RuntimeError(
                f"{self._tool_binary}: exited with code {proc.returncode}: {stderr_text}"
            )

        raw = stdout.decode(errors="replace")
        if not raw.strip():
            raise ValueError(f"{self._tool_binary}: empty output")

        return self._parse_output(raw)


class ClaudeCodeCLIProvider(CodingToolCLIProvider):
    """LLM provider that delegates to the Claude Code CLI.

    Requires `claude` to be installed and authenticated.
    Usage: set provider = "claude-code" in .synthadoc/config.toml.
    """
    _tool_binary = "claude"

    def _build_command(self) -> list[str]:
        cmd = ["claude", "-p", "--output-format", "json"]
        if self._model:
            cmd += ["--model", self._model]
        return cmd

    def _parse_output(self, raw: str) -> CompletionResponse:
        try:
            data = _json.loads(raw.strip())
        except _json.JSONDecodeError as exc:
            raise ValueError(f"claude: malformed JSON output: {exc}") from exc
        if data.get("is_error"):
            raise RuntimeError(f"claude: {data.get('result', 'unknown error')}")
        text = data.get("result", "")
        if not text:
            raise ValueError("claude: empty result in JSON output")
        return CompletionResponse(
            text=text,
            input_tokens=int(data.get("total_input_tokens", 0)),
            output_tokens=int(data.get("total_output_tokens", 0)),
        )

    def _is_quota_exhausted(self, stderr: str) -> bool:
        lower = stderr.lower()
        return any(phrase in lower for phrase in (
            "usage limit", "usage cap", "quota exceeded",
            "claude ai usage limit", "you've reached your",
        ))


class OpencodeProvider(CodingToolCLIProvider):
    """LLM provider that delegates to the Opencode CLI.

    Requires `opencode` to be installed and authenticated.
    Usage: set provider = "opencode" in .synthadoc/config.toml.
    Output is newline-delimited JSON (JSONL); text events are concatenated.
    """
    _tool_binary = "opencode"

    def _build_command(self) -> list[str]:
        cmd = ["opencode", "run", "--format", "json"]
        if self._model:
            cmd += ["--model", self._model]
        return cmd

    def _parse_output(self, raw: str) -> CompletionResponse:
        text_parts: list[str] = []
        input_tokens = 0
        output_tokens = 0
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "text":
                text_parts.append(event.get("data", ""))
            elif etype == "step_finish":
                if event.get("reason") == "error":
                    raise RuntimeError("opencode: step finished with error")
                tokens = event.get("tokens") or {}
                input_tokens = int(tokens.get("input", 0))
                output_tokens = int(tokens.get("output", 0))
        if not text_parts:
            raise ValueError("opencode: no text events in JSONL output")
        return CompletionResponse(
            text="".join(text_parts),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _is_quota_exhausted(self, stderr: str) -> bool:
        lower = stderr.lower()
        return any(phrase in lower for phrase in (
            "usage limit", "quota exceeded", "plan limit",
            "usage limit exceeded", "subscription limit",
        ))
