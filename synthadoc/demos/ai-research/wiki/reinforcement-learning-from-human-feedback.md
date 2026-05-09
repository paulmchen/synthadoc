---
title: Reinforcement Learning from Human Feedback
tags: [rlhf, alignment, training, llm]
status: active
confidence: high
created: 2026-05-09
sources:
  - file: raw_sources/ai-fundamentals-overview.md
    hash: a3f8c2d1e4b9071652340abc98def765a3f8c2d1e4b9071652340abc98def765
    size: 3847
    ingested: '2026-05-09'
orphan: false
aliases: [RLHF]
---

# Reinforcement Learning from Human Feedback

Reinforcement learning from human feedback (RLHF) is a training technique that uses human
preference data to align a language model's outputs with human values and intent. It became
the standard alignment method after InstructGPT (Ouyang et al., 2022) demonstrated that a
fine-tuned 1.3B model could outperform GPT-3 (175B) on human-preference evaluations.

## The Three-Stage Pipeline

**Stage 1 — Supervised Fine-Tuning (SFT):**  
A pre-trained base model is fine-tuned on human-written demonstrations of desired behaviour.
This produces a model that roughly follows instructions.

**Stage 2 — Reward Model Training:**  
Human labellers rank multiple model responses to the same prompt from best to worst. A
separate reward model (RM) is trained to predict these rankings, learning a scalar score
representing human preference.

**Stage 3 — RL Optimisation (PPO):**  
The SFT model is further fine-tuned using Proximal Policy Optimisation (PPO), treating
the reward model's score as the reward signal. A KL-divergence penalty prevents the model
from diverging too far from the SFT baseline (reward hacking).

## Applications

- **InstructGPT / ChatGPT** — the first large-scale deployment; established RLHF as a
  practical alignment technique
- **Claude (Anthropic)** — uses Constitutional AI (CAI) as an extension of RLHF, replacing
  some human preference labels with AI-generated feedback
- **Llama 2 Chat** — Meta's open-weight RLHF-aligned model series

## Limitations

- **Reward hacking** — the model learns to maximise the reward model's score rather than
  genuine quality; requires careful KL penalties and iterative reward model updates
- **Labeller variance** — human preferences are inconsistent; reward model quality is
  bounded by labeller agreement
- **Cost** — collecting high-quality preference data at scale is expensive

DPO (Direct Preference Optimisation) has emerged as a simpler alternative — see
[[training-techniques]] for a comparison.

## See Also

- [[training-techniques]] — RLHF in context of the full training pipeline
- [[large-language-models]] — models aligned with RLHF
