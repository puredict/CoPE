# Embodied formal v2 analyzer adversarial audit

Date: 2026-08-04

## Decision

**PASS after evidence-integrity amendment.** The task-0 five-arm analyzer now
rejects corrupted or causally impossible result tables before calculating a
CoPE advantage.

## Gaps closed

The earlier analyzer enforced cell completeness, five-arm common-input hashes,
prefix equality, zero retries, and valid event-2 skips. It did not require
manifest-equal task/state metadata, SHA-256-shaped evidence, canonical boolean
encodings, or the forward causal rule that event 2 cannot be called after an
event-1 semantic failure.

The amendment adds:

- exact task ID, state ID, prefix orientation, and sequence type matching the
  frozen manifest;
- canonical boolean values for every analyzed flag;
- SHA-256 validation for common inputs and shared action/simulator prefixes;
- positive proposal length plus proposal/response hashes for parsed calls;
- logical-before/logical-after hashes and empty failure class for semantic
  calls;
- parser -> semantic -> outcome flag coherence;
- bidirectional event dependency: event 2 is called exactly when event 1 is
  parser- and semantic-valid; otherwise it must be the fixed dependency skip.

## Adversarial cases

Focused tests reject missing cells, task/state metadata drift, invalid boolean
encodings, missing prefix/input/proposal/logical evidence, and an event-2 call
after an event-1 semantic failure. A realistic HTTP-503 event-1 failure plus
dependency skip remains classified as infrastructure-invalid rather than a
method loss.

## Verification

- focused embodied-v2 analyzer tests: 11 passed;
- provider calls: 0;
- simulator states indexed: 0;
- task-1 state 33 retries: 0;
- task-1 states 34--49 indexed: 0.

## Claim impact

No statistical threshold, prompt, arm, or outcome was changed. This amendment
only removes false-positive and corrupted-artifact paths before the embodied
run is unlocked.
