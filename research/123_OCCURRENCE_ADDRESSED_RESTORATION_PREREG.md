# Occurrence-addressed restoration development preregistration

Date: 2026-08-04  
Status: frozen before implementation and before any new task-7 rollout

## Motivation

The task-7 candidate was stopped because the old design referenced absent
`butter_1`, not because basket execution failed. The scene contains exactly
`alphabet_soup_1`, `cream_cheese_1`, and `tomato_sauce_1`. These three objects
support a more diagnostic dependent sequence:

1. preserve witnessed `in(alphabet_soup_1, basket)`;
2. replace pending cream cheese occurrence 1 with tomato sauce occurrence 1;
3. replace tomato sauce occurrence 1 with a **new cream cheese occurrence 2**.

The current sequential state uses object-derived commitment IDs and correctly
rejects this as historical-ID reuse. That exposes a real representation gap:
the same predicate can become an authorized task commitment again at a later
temporal occurrence. Reactivating the old record would corrupt lifetime and
provenance; creating an occurrence-addressed record preserves both.

## Fixed hypothesis

This does not replace CoPE's core hypothesis. It tests whether editing
persistent commitments requires addressing commitment occurrences, rather
than identifying them only by predicate arguments.

## Development-only symbolic gate

Implement a separate occurrence-addressed sequence schema without modifying
the frozen formal-v2 semantics or results. Commitment IDs have the canonical
form `<predicate-id>@<positive occurrence>`. Events explicitly name the target
and replacement occurrence IDs. The second replacement must:

- leave cream-cheese occurrence 1 historically superseded;
- supersede tomato-sauce occurrence 1;
- insert active cream-cheese occurrence 2;
- compile to `place_in(cream_cheese_1, basket_1_contain_region)`;
- preserve the satisfied alphabet-soup commitment;
- maintain revision, lifetime, supersession, and hash continuity.

Test CoPE, neutral JSON transaction, governed delta, FSR-PC, and full replan
with oracle-correct proposals. All five must materialize the identical
canonical state; no provider or simulator may be used. Include negative cases
for reactivating occurrence 1, duplicate occurrence 2, wrong target
occurrence, stale revision, and omission of the superseded historical record.

## Decision rule

- Any arm structurally unable to represent the correct state blocks learned or
  embodied comparison and is reported as interface incompetence.
- A five-arm symbolic PASS authorizes only a task-7 state-0 physical substrate
  preregistration. It does not authorize task-7 states 1--49 or provider calls.
- No result may be described as a learned advantage or publication GO.

## Novelty boundary

This experiment can support a narrow claim about occurrence identity as a
necessary representation for recurring commitments. It cannot by itself show
that CoPE labels are necessary, because generic transactions and governed
deltas may express the same occurrence-addressed state.
