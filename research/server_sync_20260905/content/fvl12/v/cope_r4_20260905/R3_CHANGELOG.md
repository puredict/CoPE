# r3 additions over final-v8

- Added a task state whose nested override chain and bound continuation are
  necessary for final physical success.
- Added fixed-LLM CoPE patch and FSR-PC full-state adapters.
- Strengthened FSR-PC by allowing stable IDs, full history, and full lineage.
- Added strict JSON, graph, lifecycle-prefix, and transition validation.
- Counted timeout, truncation, parse failure, and schema failure directly in
  end-to-end task completion.
- Added the small-state, valid-lineage, and long-lineage registered profiles.
- Added symbolic plumbing and real LIBERO/MuJoCo oracle-controller backends.
- Added paired analysis, exact McNemar inference, Wilson intervals, paired
  bootstrap intervals, and the conditional-valid diagnostic.
- Added raw per-call outputs, prompt/input hashes, state snapshots, action logs,
  result schemas, preflight, nominal gate, validation, packaging, and GPU scripts.
- Added a causal task gate that proves flattening lineage preserves the first
  surface action but changes the continuation and fails exact task completion.
- Added a compile-checked LaTeX experiment write-up that separates engineering
  verification from the pending fixed-model empirical result.
- Preserved every supplied r2 final-v8 file byte-for-byte.
