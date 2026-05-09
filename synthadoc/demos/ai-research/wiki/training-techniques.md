---
title: Training Techniques
tags: [training, fine-tuning, alignment, llm]
status: active
confidence: high
created: 2026-05-09
sources:
  - file: raw_sources/ai-fundamentals-overview.md
    hash: a3f8c2d1e4b9071652340abc98def765a3f8c2d1e4b9071652340abc98def765
    size: 3847
    ingested: '2026-05-09'
  - file: raw_sources/deep-learning-concepts.pptx
    hash: c9d2b153e6a4f807851234dab56efc90c9d2b153e6a4f807851234dab56efc90
    size: 44032
    ingested: '2026-05-09'
orphan: false
aliases: []
---

# Training Techniques

Modern [[large-language-models]] are trained in multiple stages, each addressing a
different objective — from learning general language structure to following specific
instructions safely and helpfully.

## Pre-training

Pre-training is unsupervised training on a large corpus using a self-supervised objective.
For decoder-only models (GPT family), this is *next-token prediction*: given a sequence
of tokens, predict the next one. For encoder models (BERT), it is *masked language
modelling*: predict randomly masked tokens.

Pre-training consumes the majority of compute. It instils broad world knowledge,
reasoning patterns, and language capability into the model weights.

## Supervised Fine-Tuning (SFT)

After pre-training, the base model is fine-tuned on curated (instruction, response) pairs
to produce a model that follows instructions rather than just completing text. SFT is fast
relative to pre-training and can shift model behaviour significantly with relatively few
high-quality examples.

## Reinforcement Learning from Human Feedback

[[reinforcement-learning-from-human-feedback]] (RLHF) goes further by training a reward
model from human preference comparisons, then using RL to optimise the language model
against that reward. This is the technique behind InstructGPT, ChatGPT, and early Claude
models.

## Direct Preference Optimisation (DPO)

DPO (Rafailov et al., 2023) achieves similar alignment results to RLHF without requiring
a separate reward model or RL training loop. It directly optimises the language model on
preference pairs using a cross-entropy objective, making it simpler and more stable.
Many recent open-weight models (Llama 3 Instruct, Mistral Instruct) use DPO.

## Continued Pre-training and Domain Adaptation

A base model can be further pre-trained on domain-specific corpora (legal, medical, code)
to improve specialist performance before instruction fine-tuning. This approach is
cheaper than training a specialist model from scratch.

## See Also

- [[reinforcement-learning-from-human-feedback]] — the full RLHF pipeline
- [[large-language-models]] — models produced by these techniques
- [[scaling-laws]] — how training data volume interacts with model size
