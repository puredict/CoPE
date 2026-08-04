# Occurrence held-out confirmation v3 preregistration

Freeze point: before any v3 provider request. Date: 2026-08-04.

## Purpose

Test whether CoPE's first-draw reliability and locality advantage survives a
field-complete, mechanically unambiguous comparison on cases whose object
vocabulary was absent from v1/v2. V3 is confirmatory relative to its frozen
manifest and contracts, while acknowledging that its design was informed by
the completed v1/v2 diagnostics.

## Fixed design

- 40 cases: 10 held-out triples times recurrence depths 1--4.
- Five paired arms per case: CoPE, neutral JSON transaction, governed delta,
  FSR-PC complete semantic state, and full replan.
- Model: `qwen/qwen3.5-flash-02-23`; temperature 0; one request per cell;
  zero retries; 200 planned calls.
- Arm position is balanced: every arm appears eight times in every position.
- The common recovery input is byte-identical across arms within a case.
- The seven v3 object IDs are disjoint from the seven v1/v2 object IDs.
- Before requests, the symbolic benchmark's fixed object allowlist and display
  labels are extended with those seven IDs. This changes no transition rule,
  materializer, validator, oracle, or scoring rule.
- CoPE and all controls name the actual input fields
  `event.target_commitment_id`, `event.replacement_commitment_id`, and
  `event.valid_from_state_version`.
- The neutral add-path grammar includes a synthetic literal example and bans a
  trailing slash. The example uses no v3 case object.
- Contracts, contract hashes, manifest bytes/hash, runtime commit, provider
  protocol, materializers, validators, and analyzer are frozen before launch.

## Outcomes and gate

Complete success requires parse, semantic materialization, canonical-state,
history, and directive validity on the single draw. Infrastructure failures
invalidate the run; model semantic failures do not.

Both primary controls must independently satisfy all of:

1. Holm-adjusted exact paired efficacy p-value below 0.05.
2. Paired success-rate advantage for CoPE at least 0.15.
3. No excess CoPE history or invariant failures.
4. Among pairs where both outputs materialize, Holm-adjusted locality p-value
   below 0.05.
5. Median relative CoPE proposal-byte reduction at least 0.20.

FSR-PC and full replan are secondary and cannot rescue a failed primary gate.
No response repair, path normalization, second draw, case deletion, analyzer
change, or outcome-dependent prompt change is permitted.

## Decision rule

- Joint primary pass with no new asymmetry: necessary symbolic gate passes;
  proceed to model replication and then embodied testing.
- Either primary fails because the control closes the gap: reject the claimed
  general first-draw interface advantage at this scale.
- Either primary fails through a newly discovered mechanical ambiguity:
  report v3 as inconclusive; do not silently repair it and do not count a
  counterfactual as confirmatory evidence.
- Infrastructure failure: invalidate and resume only under the frozen
  crash-recovery protocol.
