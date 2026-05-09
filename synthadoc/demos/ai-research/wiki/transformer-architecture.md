---
title: Transformer Architecture
tags: [architecture, transformers, attention, nlp]
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

# Transformer Architecture

The transformer is the dominant neural network architecture for natural language processing
and, increasingly, for vision, audio, and multimodal tasks. Introduced in the 2017 paper
*Attention Is All You Need* by Vaswani et al., it replaced recurrent networks (RNNs and
LSTMs) as the foundation for large-scale language models.

## Core Components

The transformer consists of an encoder-decoder structure, though many modern models use
only the decoder (GPT family) or only the encoder (BERT family).

1. **Tokenisation** — input text is split into subword tokens via BPE or SentencePiece
2. **Embedding layer** — tokens are mapped to dense vectors; positional encodings are added
3. **Multi-head self-attention** — each token attends to all others in the sequence
4. **Feed-forward network** — a two-layer MLP applied position-wise after attention
5. **Layer normalisation** — applied before or after each sub-layer (pre-norm vs post-norm)
6. **Residual connections** — stabilise gradient flow through deep stacks

## Why It Replaced RNNs

RNNs process tokens sequentially, preventing parallelisation during training. The
transformer's self-attention operates over the full sequence in parallel, enabling training
on orders-of-magnitude more data. Long-range dependencies — previously a weakness of RNNs
— are handled directly by [[attention-mechanisms]].

## Key Variants

- **GPT (decoder-only)** — autoregressive, trained to predict the next token
- **BERT (encoder-only)** — masked language modelling, suited for classification tasks
- **T5/BART (encoder-decoder)** — sequence-to-sequence tasks like translation and summarisation

## Scaling and Modern Extensions

The transformer has scaled remarkably well. [[scaling-laws]] established that performance
improves predictably with model size, dataset size, and compute budget. Extensions include
sparse attention for long contexts, mixture-of-experts (MoE) for parameter efficiency, and
rotary positional embeddings (RoPE) for better length generalisation.

## See Also

- [[attention-mechanisms]] — the mechanism at the core of the transformer
- [[large-language-models]] — how transformers became the foundation for LLMs
- [[training-techniques]] — how transformers are pre-trained and fine-tuned
