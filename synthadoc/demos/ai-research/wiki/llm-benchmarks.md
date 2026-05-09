---
title: LLM Benchmarks
tags: [benchmarks, evaluation, llm]
status: active
confidence: medium
created: 2026-05-09
sources:
  - file: raw_sources/model-capabilities-comparison.xlsx
    hash: b7e1a042c5d3f896740123cde45fab89b7e1a042c5d3f896740123cde45fab89
    size: 9214
    ingested: '2026-05-09'
orphan: false
aliases: []
---

# LLM Benchmarks

Benchmarks provide standardised evaluations of language model capabilities across
reasoning, knowledge, coding, and instruction-following tasks. Benchmark results are
widely cited in model release announcements, though their validity as proxies for
real-world usefulness is actively debated.

## Key Benchmarks

**MMLU (Massive Multitask Language Understanding)**  
A 57-subject multiple-choice test covering STEM, humanities, law, and social sciences.
Commonly used as a broad knowledge and reasoning proxy. Human expert performance is
approximately 89.8%.

**HumanEval**  
A Python coding benchmark from OpenAI comprising 164 hand-written programming problems.
Models are evaluated on whether their generated code passes hidden unit tests (pass@1).

**MATH**  
Competition mathematics problems (AMC, AIME, MATH levels 1–5). Tests multi-step symbolic
reasoning. Scores below 50% were common on frontier models before chain-of-thought
prompting.

**HELM (Holistic Evaluation of Language Models)**  
A Stanford framework that evaluates models across dozens of scenarios using accuracy,
calibration, robustness, fairness, and efficiency metrics simultaneously.

## Reported Results (as of early 2026)

| Model         | MMLU (5-shot) | HumanEval | Notes                              |
|---------------|---------------|-----------|------------------------------------|
| GPT-4         | 86.4%         | 67.0%     | OpenAI technical report (2023)     |
| Claude 3 Opus | 86.8%         | 84.9%     | Anthropic model card (2024)        |
| Gemini Ultra  | 90.0%         | 74.4%     | Google technical report (2023)     |
| Llama 3 70B   | 82.0%         | 81.7%     | Meta release (2024)                |

Gemini Ultra's 90.0% MMLU score is the first result to surpass human expert performance
(89.8%) on this benchmark, marking a significant milestone in language model evaluation.

## Benchmark Limitations

Benchmark saturation occurs when frontier models consistently score above 90% on a task,
reducing its discriminative value. MMLU is approaching this threshold for top models.
There is also ongoing concern about data contamination — model training corpora may
include benchmark questions, inflating scores.

## See Also

- [[large-language-models]] — the models being evaluated
- [[training-techniques]] — how training choices affect benchmark performance
