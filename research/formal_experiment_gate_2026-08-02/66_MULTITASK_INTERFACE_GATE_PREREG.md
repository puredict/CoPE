# Multi-task oracle-correct interface gate preregistration

Status: frozen before execution; zero provider and zero simulator states.

## Purpose

Before any task-0/task-7 rollout or model call, prove that CoPE, neutral patch,
compact transaction and FSR-PC can all express and validate the same canonical
replacement/cancellation outcomes.  This prevents structural interface
incompetence from being misreported as method failure.

## Frozen cases

The exact four rows are in `manifests/multitask_interface_gate_v1.csv`:

- task 0, alphabet soup witnessed done, tomato sauce pending: replace tomato
  sauce with cream cheese; and cancel tomato sauce;
- task 7, alphabet soup witnessed done, cream cheese pending: replace cream
  cheese with butter; and cancel cream cheese.

No LIBERO initial-state array is loaded.  The gate operates on canonical
persistent symbolic states only.

## Arms and equality gate

For each case inject an oracle-correct output through each arm's real parser,
materializer and semantic validator:

1. CoPE typed `Override`/`Expire` patch;
2. neutral `N01`/`N02` sparse patch translated by the frozen neutral bridge;
3. generic compact transaction containing only allowlisted semantic writes;
4. FSR-PC complete metadata-free semantic state.

All four must produce the identical canonical post-state hash and compiled
directive.  Completed progress must remain true, superseded commitments must be
inactive, provider calls must equal zero, and no task state may be indexed.

Any failure blocks the future formal study and must be repaired without formal
states or provider calls.  Passing authorizes only task-specific prefix
development on states 0--9, not formal states 10--29.

