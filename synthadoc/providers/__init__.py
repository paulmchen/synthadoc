# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import os
from synthadoc.config import Config, AgentConfig
from synthadoc.providers.base import LLMProvider
from synthadoc import errors as E


def _require_env(var: str, provider: str, url: str) -> str:
    value = os.environ.get(var, "").strip()
    if not value:
        E.cli_error(
            E.CFG_MISSING_API_KEY,
            f"{var} is not set. synthadoc uses {provider} as its LLM provider.",
            f"  1. Get your API key at: {url}\n"
            f"  2. Set it for the current session:\n"
            f"       Linux / macOS:   export {var}=<your-key>\n"
            f"       Windows cmd.exe: set {var}=<your-key>\n"
            f"       PowerShell:      $env:{var}='<your-key>'\n"
            f"  3. To persist across sessions:\n"
            f"       Linux / macOS:  echo 'export {var}=<your-key>' >> ~/.bashrc\n"
            f"       Windows:        [System.Environment]::SetEnvironmentVariable('{var}', '<your-key>', 'User')\n"
            f"  Alternatively, set provider = \"ollama\" in .synthadoc/config.toml to use a local model.",
        )
    return value


def make_provider(agent_name: str, config: Config) -> LLMProvider:
    agent_cfg = config.agents.resolve(agent_name)
    timeout = config.agents.llm_timeout_seconds
    name = agent_cfg.provider
    if name == "anthropic":
        from synthadoc.providers.anthropic import AnthropicProvider
        key = _require_env("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/")
        return AnthropicProvider(api_key=key, config=agent_cfg)
    if name == "openai":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys")
        return OpenAIProvider(api_key=key, config=agent_cfg, timeout=timeout)
    if name == "gemini":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("GEMINI_API_KEY", "Google Gemini",
                           "https://aistudio.google.com/app/apikey")
        cfg_with_url = AgentConfig(
            provider="gemini", model=agent_cfg.model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == "groq":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("GROQ_API_KEY", "Groq", "https://console.groq.com/keys")
        cfg_with_url = AgentConfig(
            provider="groq", model=agent_cfg.model,
            base_url="https://api.groq.com/openai/v1",
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == "minimax":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("MINIMAX_API_KEY", "MiniMax", "https://platform.minimax.io/")
        cfg_with_url = AgentConfig(
            provider="minimax", model=agent_cfg.model,
            base_url="https://api.minimax.io/v1",
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == "deepseek":
        from synthadoc.providers.openai import OpenAIProvider
        key = _require_env("DEEPSEEK_API_KEY", "DeepSeek", "https://platform.deepseek.com/api_keys")
        cfg_with_url = AgentConfig(
            provider="deepseek", model=agent_cfg.model,
            base_url="https://api.deepseek.com/v1",
        )
        return OpenAIProvider(api_key=key, config=cfg_with_url, timeout=timeout)
    if name == "ollama":
        from synthadoc.providers.ollama import OllamaProvider
        return OllamaProvider(config=agent_cfg)
    E.cli_error(E.CFG_UNKNOWN_PROVIDER, f"Unknown provider: {name!r}",
                "Supported providers: anthropic, openai, gemini, groq, minimax, deepseek, ollama")
