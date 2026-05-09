---
title: Large Language Models
tags: [llm, transformers, gpt, language-models]
status: active
confidence: high
created: 2026-05-09
sources:
  - file: raw_sources/ai-fundamentals-overview.md
    hash: a3f8c2d1e4b9071652340abc98def765a3f8c2d1e4b9071652340abc98def765
    size: 3847
    ingested: '2026-05-09'
  - file: raw_sources/model-capabilities-comparison.xlsx
    hash: b7e1a042c5d3f896740123cde45fab89b7e1a042c5d3f896740123cde45fab89
    size: 9214
    ingested: '2026-05-09'
orphan: false
aliases: []
---

# Large Language Models

Large language models (LLMs) are [[transformer-architecture]]-based models trained on
massive text corpora to predict the probability of the next token. At sufficient scale,
this simple objective produces models capable of reasoning, code generation, translation,
and open-ended instruction following.

## The Scale Threshold

Early transformers (BERT, GPT-2) demonstrated strong performance on specific tasks but
required task-specific fine-tuning. GPT-3 (Brown et al., 2020), with 175 billion
parameters, showed that a sufficiently large model could perform novel tasks from a few
examples in the prompt — a property called *few-shot in-context learning*. This established
a qualitative shift: scale itself became a training strategy. [[scaling-laws]] formalised
why this works.

## Landmark Models

| Model       | Organisation  | Parameters | Key contribution                          |
|-------------|---------------|------------|-------------------------------------------|
| GPT-3       | OpenAI        | 175B       | In-context learning at scale              |
| BERT        | Google        | 340M       | Masked LM, encoder-only pretraining       |
| PaLM        | Google        | 540B       | Chain-of-thought reasoning at scale       |
| LLaMA 2     | Meta          | 7B–70B     | Open-weights, commercially permissive     |
| Claude 3    | Anthropic     | Undisclosed| Constitutional AI alignment               |
| GPT-4       | OpenAI        | Undisclosed| Multimodal, strong reasoning              |
| Gemini      | Google        | Undisclosed| Multimodal from the ground up             |

## Instruction Tuning and Alignment

Base LLMs predict next tokens; they do not follow instructions reliably. Two techniques
bridge the gap:

- **Instruction fine-tuning** — supervised fine-tuning on (instruction, response) pairs
- **RLHF** — [[reinforcement-learning-from-human-feedback]] refines behaviour using human
  preference signals; used in InstructGPT, ChatGPT, and Claude

## Context Windows

Early LLMs were limited to 2K–4K token contexts. Modern models (GPT-4 Turbo, Claude 3,
Gemini 1.5 Pro) support 128K–1M tokens, enabling full-document reasoning and long-session
memory.

## See Also

- [[transformer-architecture]] — the architecture all major LLMs share
- [[scaling-laws]] — why bigger models trained on more data perform better
- [[training-techniques]] — how LLMs are pre-trained and aligned
- [[llm-benchmarks]] — how LLM capabilities are measured and compared
