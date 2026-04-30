# Coding Tool CLI Provider — Design v0.3.0

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users with a Claude Code or Opencode subscription to run Synthadoc without a separate LLM API key, by delegating all LLM calls to the coding tool's CLI. All existing provider behaviour is unchanged.

**Architecture:** New `CodingToolCLIProvider` abstract base class with two concrete subclasses (`ClaudeCodeCLIProvider`, `OpencodeProvider`). Codex added in v0.4.0 as a third subclass.

**Tech Stack:** Python `asyncio.create_subprocess_exec`, `shutil.which`, existing `LLMProvider` ABC, `providers/__init__.py` factory, `synthadoc serve --provider` override flag.

---

## 1. Architecture

```
LLMProvider (ABC)                      ← unchanged
├── AnthropicProvider                  ← unchanged
├── OpenAIProvider                     ← unchanged
├── OllamaProvider                     ← unchanged
└── CodingToolCLIProvider (new)        ← abstract base; owns subprocess mechanics
    ├── ClaudeCodeCLIProvider          ← v0.3.0; claude -p "{prompt}" --output-format json
    └── OpencodeProvider               ← v0.3.0; opencode run "{prompt}" --format json (JSONL)
    # CodexProvider                    ← v0.4.0
```

`CodingToolCLIProvider` implements `complete()` by:
1. Calling `_build_command(prompt, system, max_tokens) → list[str]` (abstract, per-tool)
2. Spawning the subprocess via `asyncio.create_subprocess_exec`
3. Passing the prompt via **stdin** (not CLI argument) to avoid OS argument length limits
4. Enforcing `llm_timeout_seconds` via `asyncio.wait_for`
5. Checking exit code + stderr
6. Calling `_parse_output(raw: str) → CompletionResponse` (abstract, per-tool)

Both subclasses set `supports_vision = False`. The `embed()` method raises `NotImplementedError` — vector search falls back to BM25-only automatically (existing behaviour).

### ClaudeCodeCLIProvider

- Command: `claude -p --output-format json [--model <model>]`
- Prompt passed via stdin
- Output: single JSON object; extract `result` or `content` field for text, token fields for counts

### OpencodeProvider

- Command: `opencode run --format json [--model <model>]`
- Prompt passed via stdin
- Output: newline-delimited JSON (JSONL) stream; collect all `type: "text"` event `data` fields; read `tokens` from `type: "step_finish"` event

---

## 2. Configuration

No new config keys. Users set `provider = "claude-code"` or `provider = "opencode"` in `.synthadoc/config.toml`:

```toml
# Option A — per-agent (mix providers)
[agents.ingest]
provider = "claude-code"
model = "claude-sonnet-4-5"   # optional — uses tool's configured default if omitted

[agents.query]
provider = "claude-code"

[agents.lint]
provider = "claude-code"

# Option B — global default (all agents)
[agents]
provider = "claude-code"
```

`model` is passed as `--model <value>` to the CLI. If omitted, the tool uses its own configured default.

No API key environment variables are required or checked for either provider.

---

## 3. Agent Compatibility

All three agents work unchanged — they call `provider.complete()` with no knowledge of what's underneath.

| Agent | LLM calls | Notes |
|---|---|---|
| IngestAgent | 2–3 per source (analyse + decide + optional YouTube summary) | Multiple sequential subprocess calls; slower than direct API for large batches — document this |
| QueryAgent | 1–2 per query (decompose + synthesise) | No issues |
| LintAgent | 0 for `lint report`; 1 per contradicted page for `auto-resolve` | `lint report` never needs a provider |

Vector search (`embed()`) falls back to BM25-only silently — no user action needed.

---

## 4. Error Handling

| Failure | Detection | Exception | Job outcome |
|---|---|---|---|
| Binary not found | `shutil.which()` at construction | `EnvironmentError` with install hint | Fails before job starts |
| Subprocess exits non-zero | Exit code check | `RuntimeError(stderr)` | Job marked `failed` |
| Empty or malformed output | `_parse_output` validation | `ValueError` | Job marked `failed` |
| Timeout | `asyncio.wait_for` | `TimeoutError` | Job marked `failed` |
| Quota exhausted | `_is_quota_exhausted(stderr) → bool` per subclass | `ProviderQuotaExhaustedError` | Job marked `quota_exhausted` |

`ProviderQuotaExhaustedError` is a new exception class. The job orchestrator catches it specifically and sets `skip_reason = "quota_exhausted"` with a user message:

```
Job failed: Claude Code usage quota exhausted.
Wait for quota to reset, then retry:
  synthadoc ingest <source> -w my-wiki
Or switch provider temporarily:
  synthadoc serve -w my-wiki --provider anthropic
```

No retries at the provider level — consistent with all existing providers.

---

## 5. `--provider` Override on `synthadoc serve`

```bash
synthadoc serve -w my-wiki --provider anthropic
```

Overrides the `provider` field in `config.toml` for all agents for the lifetime of that server process. Useful when the coding tool quota is exhausted and the user wants to temporarily use a direct API provider without editing config.

Unknown `--provider` value → clear error with supported list before server starts.

---

## 6. Performance

**Goal:** CLI provider adds ≤ 10s of subprocess startup overhead per ingest job.

A single ingest job makes 2–3 LLM calls. If the direct API path takes T seconds, the CLI provider path should complete within T + 10s.

Document in Appendix E: CLI providers are suited for interactive / low-volume use. For high-volume batch ingest, a direct API provider is recommended.

---

## 7. Testing

### Unit tests (mocked subprocess — no real CLI required)

**`ClaudeCodeCLIProvider`:**
- Valid JSON output → correct `CompletionResponse`
- Error JSON (rate limit, context exceeded) → `RuntimeError`
- Missing text field → `ValueError`
- Quota exhaustion pattern in stderr → `ProviderQuotaExhaustedError`

**`OpencodeProvider`:**
- Valid JSONL (text + step_finish events) → correct `CompletionResponse` with token counts
- Zero `text` events → `ValueError`
- `step_finish` with `reason = "error"` → `RuntimeError`
- Truncated JSONL (timeout mid-stream) → `ValueError`
- Quota exhaustion pattern in stderr → `ProviderQuotaExhaustedError`

**`CodingToolCLIProvider` base:**
- Binary not found → `EnvironmentError` at construction
- Prompt longer than 32K chars → passed via stdin (not CLI arg)
- Timeout fires → `TimeoutError`
- Subprocess exits non-zero → `RuntimeError` with stderr message

**`--provider` override:**
- `synthadoc serve --provider anthropic` overrides config for all agents
- Unknown `--provider` value → `EnvironmentError` before server starts

### Performance benchmark (mocked subprocess)

- `_parse_output` on a 2000-token realistic response → completes in < 50ms

### Integration tests (`@pytest.mark.integration` — skipped in CI unless tool available)

- Real `claude -p` round-trip → `CompletionResponse.text` is non-empty
- Real `opencode run` round-trip → `CompletionResponse.text` is non-empty
- Single ingest job wall time with CLI provider ≤ direct API time + 10s

---

## 8. Documentation Updates

### `docs/design.md` — Appendix A Release Feature Index, v0.3.0

Add entry:

> **Coding tool CLI providers (`claude-code`, `opencode`)** — users with a Claude Code or Opencode subscription can set `provider = "claude-code"` (or `"opencode"`) in `config.toml` and run all three agents (ingest, query, lint) without a separate API key. `CodingToolCLIProvider` abstract base handles subprocess mechanics (stdin prompt passing, timeout, exit code, stderr capture); `ClaudeCodeCLIProvider` and `OpencodeProvider` each implement `_build_command()`, `_parse_output()`, and `_is_quota_exhausted()`. Quota exhaustion raises `ProviderQuotaExhaustedError` and marks the job `quota_exhausted` with a clear retry message. `synthadoc serve --provider <name>` overrides `config.toml` for the lifetime of the server process. Vector search falls back to BM25-only (CLI providers do not support `embed()`). Codex support planned for v0.4.0.

### `docs/user-quick-start-guide.md` — new Appendix E

Title: **Appendix E — Using a Coding Tool as Your LLM Provider**

Add one pointer sentence at the end of the installation section: *"To use Claude Code or Opencode as your LLM provider instead of an API key, see Appendix E."*

Appendix E sections:

1. **Setup** — edit `config.toml`, set `provider = "claude-code"` or `"opencode"`, no API key needed
2. **Demo: ingest + query** — show ingest URL + query; output identical to direct API provider
3. **Demo: temporary provider override** — `synthadoc serve --provider anthropic` when quota is exhausted
4. **Troubleshooting** — quota exhaustion error message, how to read it, how to recover

---

## 9. Scope

| Version | Scope |
|---|---|
| v0.3.0 | `ClaudeCodeCLIProvider`, `OpencodeProvider`, `--provider` override, Appendix E |
| v0.4.0 | `CodexProvider` (and any other coding tools with headless CLI support) |
