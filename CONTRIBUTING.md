# Contributing to Synthadoc

Thank you for your interest in contributing!

## Licensing and CLA

Synthadoc uses a split-licence model:

| Component | Licence | What this means |
|-----------|---------|-----------------|
| Core server and all other source files | AGPL-3.0-or-later | Modifications must be released under AGPL |
| `synthadoc/skills/base.py` | Apache-2.0 | Third-party skills may use **any** licence |
| `synthadoc/providers/base.py` | Apache-2.0 | Third-party providers may use **any** licence |

This means you can write and distribute custom skills or LLM providers — open source or commercial — without being bound by the AGPL, as long as you only extend the Apache-2.0 base classes and do not modify the AGPL core.

A commercial licence is available separately for enterprise use of the core.

To keep dual-licensing viable, **all contributors must sign a Contributor License Agreement (CLA)** before any pull request can be merged. The CLA grants axoviq.com the right to distribute your contribution under both the AGPL and a commercial licence, while you retain your copyright.

A CLA bot will automatically request a signature when you open your first pull request.

## How to Contribute

1. **Open an issue first** for any non-trivial change so we can discuss the approach before you invest time coding.
2. **Fork** the repository and create a feature branch from `main`.
3. **Write tests** — new behaviour must be covered; bug fixes should include a regression test.
4. **Run the test suite** locally before opening a PR:
   ```
   pytest
   ```
5. **Add SPDX headers** to any new source files you create:
   ```python
   # SPDX-License-Identifier: AGPL-3.0-or-later   # for core files
   # SPDX-License-Identifier: Apache-2.0           # for new plugin interface files
   # Copyright (C) 2026 Paul Chen / axoviq.com
   ```
6. **Open a pull request** against `main` with a clear description of what changed and why.

## Code Style

- Python: follow PEP 8; use `ruff` for linting.
- TypeScript: follow the existing eslint/prettier config in `obsidian-plugin/`.
- Keep commits focused; one logical change per commit.

## Release checklist

- [ ] Update `synthadoc/providers/pricing.py` — verify rates against provider pricing pages, update `_LAST_UPDATED`

Pricing sources to check:
- Anthropic: https://docs.anthropic.com/en/docs/about-claude/pricing
- OpenAI: https://openai.com/api/pricing/
- Gemini: https://ai.google.dev/gemini-api/docs/pricing
- Groq: https://groq.com/pricing

## Reporting Bugs

Use [GitHub Issues](../../issues). Include steps to reproduce, the full error message, and your OS / Python version.

## Security Issues

Do **not** open a public issue for security vulnerabilities. Email `security@axoviq.com` instead.
