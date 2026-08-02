# X03/X04/X08 integration and live-packet result

Date: 2026-08-02 (Asia/Shanghai)

## Decision

The bounded integration/live-packet experiment passes on already-consumed
development states 0--4.

- **X03 live predicate integration gate: CLOSED.** Ten production packets were
  emitted by the registered LIBERO predicate path and consumed by the non-fake
  validator. Every packet was bound to task, event, policy step, RGB digest,
  simulator-state digest, producer commit, and canonical packet digest. Packet
  predicates matched the independently logged predicates in 10/10 cases.
- **X04 oracle mechanism integration gate: CLOSED.** Native FSR and post-CoPE
  received byte-identical `RecoveryInput`, both produced `full-state-v2`, and
  both used the same validate-then-compile function. Canonical states, hashes,
  and directives matched in 10/10 cases. Semantic processing changed neither
  simulator state nor action count and emitted zero post-event policy actions.
- **X08 semantic-config consumption integration sub-gate: CLOSED.** The runner
  loaded the exact task-1 sidecar and recorded its SHA-256 plus the locked
  reserve-manifest SHA-256 in every row. The previously failed replacement
  updated-goal controller-competence cell was not rerun and remains open, so
  overall X08 is not claimed closed for replacement efficacy.

The authoritative run and replay are byte-identical. Targeted tests were 38/38,
the frozen independent materializer remained 4/4, the corruption audit remained
123/123 with zero malformed acceptance, and the full repository suite was
349/349.

## Scope and non-claims

This is an oracle-selected mechanism wiring result, not a learned-method result.
No real provider was called. It is not evidence that CoPE outperforms FSR-PC,
not a held-out estimate, and not a robot-task success comparison. No GPU, model
checkpoint inference, training, checkpoint download, or post-event recovery
policy action occurred. States 25--49 were not read.

## P6 cancellation-pilot unlock conditions

This integration result is necessary but not by itself permission to consume
state 26. P6 cancellation may be unlocked only after all of the following are
recorded from one final clean committed tree:

1. The X03/X04/X08 integration evidence bundle and checksums are committed and
   the clean audit verifies the exact runtime, sidecar, reserve manifest,
   checkpoint/BDDL/init-state hashes, predicate producer, and Oracle controller
   parameters.
2. The P6 runner is explicitly restricted to the reserved cancellation row for
   state 26; state 25 and states 27--49 remain inaccessible.
3. Output-create semantics and a new collision-free state-26 output directory
   are pre-registered; no existing trace or result may be overwritten.
4. Native Oracle FSR and Oracle CoPE-PATCH-HALT retain the same live observation,
   packet, `RecoveryInput`, validator/compiler, prefix, and action budget; the
   operation selector remains the fixed oracle and no learned/provider claim is
   made.
5. A fresh `nvidia-smi` check is recorded immediately before simulation and an
   idle GPU is selected only if the controller path actually requires one.
6. Readiness fails closed on dirty tree, missing config, non-live/test packet,
   incomplete provenance, input mismatch, path mismatch, simulator mutation,
   or any attempted access outside the single reserved cancellation row.

State 26 was not run in this experiment.
