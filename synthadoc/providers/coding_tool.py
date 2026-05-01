# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import json as _json
import os
import shutil
import sys
from abc import abstractmethod
from pathlib import Path
from typing import Optional

from synthadoc.providers.base import CompletionResponse, LLMProvider, Message

# Common locations where npm-installed CLIs (claude, opencode) live on macOS/Linux
# that are absent from the minimal PATH seen by GUI apps and non-login shells.
def _extra_binary_dirs() -> list[Path]:
    dirs = [
        Path.home() / ".npm" / "bin",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),        # Homebrew on Apple Silicon
        Path("/usr/local/opt/node/bin"),  # Homebrew node on Intel
        Path.home() / ".local" / "bin",
        Path.home() / ".yarn" / "bin",
        Path.home() / "bin",
    ]
    # nvm-managed node versions
    nvm_node = Path.home() / ".nvm" / "versions" / "node"
    if nvm_node.is_dir():
        dirs.extend(sorted(nvm_node.glob("*/bin")))
    return dirs


def _find_binary(name: str) -> Optional[str]:
    """Locate *name* using three escalating strategies.

    1. shutil.which with the current process PATH (fast path).
    2. shutil.which with well-known npm/nvm/Homebrew/Go directories appended.
    3. Ask the user's login shell (zsh/bash -lc "which <name>") so that
       ~/.zshrc, ~/.zprofile, ~/.bashrc etc. are sourced — handles Go, Cargo,
       custom install scripts and anything else that modifies PATH at shell init.
    """
    import subprocess

    # 1. Current PATH
    found = shutil.which(name)
    if found:
        return found

    # 2. Well-known extra dirs
    current_path = os.environ.get("PATH", "")
    extra = os.pathsep.join(
        str(d) for d in _extra_binary_dirs()
        if str(d) not in current_path and d.is_dir()
    )
    augmented = extra + os.pathsep + current_path if extra else current_path
    found = shutil.which(name, path=augmented)
    if found:
        return found

    # 3. Login shell — loads user profile so all PATH mutations are visible
    if sys.platform != "win32":
        shell = os.environ.get("SHELL", "/bin/zsh")
        try:
            result = subprocess.run(
                [shell, "-lc", f"which {name}"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                candidate = result.stdout.strip()
                if candidate and Path(candidate).is_file():
                    return candidate
        except Exception:
            pass

    return None


class CodingToolCLIProvider(LLMProvider):
    """Abstract base for coding tool CLI providers (Claude Code, Opencode, …).

    Subclasses implement _build_command, _parse_output, and _is_quota_exhausted.
    The prompt is always passed via stdin to avoid OS argument length limits.
    """
    supports_vision = False
    _tool_binary: str  # e.g. "claude" or "opencode" — set by subclass

    def __init__(self, model: Optional[str], timeout: int) -> None:
        resolved = _find_binary(self._tool_binary)
        if resolved is None:
            raise EnvironmentError(
                f"[ERR-PROV-003] '{self._tool_binary}' not found in PATH. "
                f"Install it and ensure it is authenticated before using this provider. "
                f"If it is installed, add its directory to PATH before starting synthadoc serve "
                f"(e.g. export PATH=\"$HOME/.npm/bin:$PATH\")."
            )
        # On Windows, .cmd/.bat wrappers cannot be executed directly by
        # create_subprocess_exec — they must be run via "cmd /c".
        self._cmd_prefix: list[str] = (
            ["cmd", "/c"] if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat"))
            else []
        )
        self._resolved_binary = resolved  # absolute path, avoids PATH issues at exec time
        self._model = model
        self._timeout = timeout or None

    @abstractmethod
    def _build_command(self, binary: str) -> list[str]:
        """Return the subprocess argv list using *binary* (absolute path). Prompt is via stdin."""

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
        cmd = self._cmd_prefix + self._build_command(self._resolved_binary)

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

    def _build_command(self, binary: str) -> list[str]:
        cmd = [binary, "-p", "--output-format", "json"]
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

    def _build_command(self, binary: str) -> list[str]:
        cmd = [binary, "run", "--format", "json"]
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
