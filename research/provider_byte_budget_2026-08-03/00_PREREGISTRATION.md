# X19 provider-visible byte-budget preregistration

Frozen: 2026-08-03 before running the accounting program.

## Question

X12 compared proposal bytes but not the arm-specific output contract carried in
every provider request. Does CoPE's sparse proposal remain smaller after adding
the actual frozen provider-visible request bytes, relative to compact TX and
FSR-PC?

## Design

- exact 12-case X13 manifest and exact frozen OpenAI-compatible request builder;
- arms: CoPE patch, compact generic transaction, FSR-PC full state;
- no provider, tokenizer, GPU, simulator or reserved state;
- record UTF-8 bytes for common input, output contract, complete canonical wire
  request, canonical oracle proposal, and request plus oracle proposal;
- verify common-input hashes match within every triplet;
- aggregate medians and sums without dropping no-op or invalid-event cases.

## Interpretation

This measures serialization bytes only. It does not estimate provider token
counts, KV-cache cost, latency, correctness or learned generation difficulty.
If CoPE loses after request-contract overhead, any output-efficiency claim must
be restricted to reusable-schema or constrained-decoding settings. If it wins,
the result remains a deterministic accounting claim pending real provider
usage.
