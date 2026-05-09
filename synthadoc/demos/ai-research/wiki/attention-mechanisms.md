---
title: Attention Mechanisms
tags: [architecture, attention, transformers, nlp]
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

# Attention Mechanisms

Attention allows a neural network to focus on the most relevant parts of its input when
producing each element of its output. It was originally proposed for sequence-to-sequence
models (Bahdanau et al., 2014) as a way to help encoders handle long sequences, and was
later generalised into the self-attention mechanism at the heart of the [[transformer-architecture]].

## Scaled Dot-Product Attention

The standard attention operation takes three matrices — queries (Q), keys (K), and values
(V) — and computes:

```
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V
```

The scaling factor `sqrt(d_k)` prevents the dot products from growing large in high
dimensions, which would push the softmax into regions with very small gradients.

## Multi-Head Attention

Rather than performing a single attention pass, transformers run attention in parallel
across multiple "heads", each learning different relationship patterns. The outputs are
concatenated and projected back to the model dimension. Multi-head attention allows the
model to jointly attend to information from different representation subspaces.

## How Attention Changed Language Model Training

Before self-attention, RNNs were forced to compress all context into a fixed-size hidden
state before decoding — a bottleneck that degraded performance on long sequences. Attention
lets every token directly access every other token in the sequence in a single operation.
This had two major consequences:

1. **Full parallelisation** — the attention matrix is computed in one pass over the full
   sequence, enabling GPU-parallel training at scale
2. **No vanishing gradient over distance** — long-range dependencies are as easy to learn
   as short-range ones

Together, these properties enabled the shift from RNN-based models to the
[[transformer-architecture]], which in turn enabled the scaling trajectory described in
[[scaling-laws]] and the emergence of [[large-language-models]].

## Key Variants

- **Cross-attention** — queries from the decoder attend to keys/values from the encoder
- **Sparse attention** — only attend to a subset of tokens (e.g. Longformer, BigBird) for
  long-context efficiency
- **Flash Attention** — a hardware-aware kernel that computes exact attention in O(N) memory
  rather than O(N²), enabling much longer context windows in practice

## See Also

- [[transformer-architecture]] — the full architecture built on multi-head attention
- [[large-language-models]] — models that rely on attention at every layer
