# CoPE formal readiness v2 decision

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**NO-GO for reserved-state learned embodied formal experiments.**

The physical mechanism substrate is now qualified and the consolidated branch
passes 445/445 tests. However, the decisive learned semantic-generation gate
still has zero real model calls, and the external runtime provenance gate has
not been regenerated to a true-clean PASS. Spending states 27--49 would answer
neither missing question.

## What is now complete

- live semantic wiring: 10/10 non-fake predicate packet development cases;
- privileged controller/mechanism substrate: 75 assigned episodes, zero
  method-independent pre-event failures, 35/35 paired provenance groups;
- tri-arm provider fairness and mocked transport controls;
- exact, generic-transaction, typed-patch and full-state execution paths;
- decomposed validator: original random fuzzing found 24 false accepts, the
  scoped repair removed them, and an unseen seed achieved 2,992/2,992 parity
  on changed candidates;
- consolidated implementation regression: 445/445 tests.

## What the evidence has falsified or narrowed

- CoPE is not uniquely expressive: generic compact transactions reproduce the
  frozen transitions.
- Zero fail-open under the tested guards is not typing-specific once equivalent
  canonical guards are supplied to all arms.
- CoPE's size advantage is sparse-regime-specific and reverses at dense edits;
  commit/memory costs are not generally better.
- The first decomposed validator was incomplete despite passing hand-designed
  cases; the retained X18 failure demonstrates why formal self-falsification is
  necessary.

Therefore the only viable method-paper discriminator left is **learned output
factorization**: under the same capable semantic model and same input, does a
CoPE patch have higher first-pass semantic correctness or lower generation and
repair cost than both a compact generic transaction and an FSR-PC full state?

## The next critical experiment

Run frozen X13, not a robot rollout:

1. model `qwen/qwen3.5-flash-02-23`, temperature 0, seed 20260802;
2. four smoke triplets first, same input bytes and rotated arm order;
3. expand to 12 triplets only if all provider calls return and all fairness
   checks pass;
4. compare CoPE, compact transaction and FSR-PC first-pass semantic correctness,
   parser failures, unauthorized/stale edits, tokens, bytes and latency;
5. if at least one arm has a usable ceiling, freeze a larger paired corpus
   before any embodied state is spent.

This experiment requires a provider credential or an explicitly authorized
already-local capable instruction model. A 0.5B checkpoint download was not
completed because the repository rules require explicit permission for a
nontrivial checkpoint download; its diagnostic cannot substitute for X13.

## Paper Go/No-Go rule

- CoPE clearly beats both strong arms: continue with the narrow learned
  factorization/assurance claim, then unlock states 27--46 after true-clean
  provenance regeneration; retain 47--49.
- CoPE ties compact TX: stop the broad CoPE-specific method claim; consider a
  representation-agnostic sparse transactional recovery paper only if the
  embodied effect is large.
- compact TX beats CoPE: redesign the representation or stop the method paper.
- all arms unusable: qualify a stronger semantic generator before any embodied
  experiment.

As of this audit, the idea is **not yet submission-supported for ICRA as a
method paper**. It is also not disproven: the decisive learned generation
comparison has not occurred.
