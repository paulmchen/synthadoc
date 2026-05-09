---
title: Scaling Laws
tags: [scaling, training, compute, llm]
status: active
confidence: high
created: 2026-05-09
sources:
  - file: raw_sources/ai-fundamentals-overview.md
    hash: a3f8c2d1e4b9071652340abc98def765a3f8c2d1e4b9071652340abc98def765
    size: 3847
    ingested: '2026-05-09'
orphan: false
aliases: []
---

# Scaling Laws

Scaling laws describe the empirical relationship between model performance and three
variables: the number of model parameters (N), the size of the training dataset (D), and
the amount of compute (C). The key finding is that loss decreases as a smooth power law
when any of these variables increases — a predictable relationship that enables
researchers to forecast model capability before training.

## Kaplan et al. (2020)

The first systematic study of neural language model scaling (OpenAI, 2020) found that:

- Loss scales as a power law in N, D, and C independently
- Model size has the largest impact per unit of compute
- Data and compute should scale together, but models were being under-trained relative
  to their size

This led to training very large models on relatively small datasets — GPT-3 (175B
parameters) was trained on roughly 300B tokens.

## Chinchilla Scaling Laws (Hoffmann et al., 2022)

The Chinchilla paper (DeepMind, 2022) revised the Kaplan findings with a more thorough
compute-optimal analysis. The key result: **for a given compute budget, model size and
training tokens should be scaled equally**. Specifically, the optimal token count is
approximately 20× the parameter count.

This implied that GPT-3 and PaLM were significantly under-trained. The Chinchilla model
(70B parameters, 1.4T tokens) outperformed the 280B Gopher model trained on the same
compute budget, validating the analysis.

## Implications for Modern Training

- LLaMA models were explicitly designed to be Chinchilla-optimal or over-trained, making
  them efficient at *inference* time (smaller model, better performance)
- Long-run training (e.g. Llama 3 on 15T tokens for a 70B model) intentionally exceeds
  Chinchilla-optimal to maximise inference efficiency at deployment scale
- Scaling laws have limits: performance on specific reasoning tasks can improve
  discontinuously (emergent abilities), not smoothly

## See Also

- [[large-language-models]] — models trained under these scaling regimes
- [[training-techniques]] — the training process scaling laws apply to
