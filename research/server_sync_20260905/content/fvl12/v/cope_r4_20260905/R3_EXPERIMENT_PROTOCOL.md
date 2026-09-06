# Registered r3 experiment protocol

## Hypothesis

Under an identical finite LLM call budget, persistent typed lifecycle editing
has higher end-to-end completion on a long task whose correct continuation is
selected by lineage than complete state regeneration.

## Independent variable

Only the state-update representation changes:

- CoPE output: minimal typed patch.
- FSR-PC output: complete state JSON.

FSR-PC is explicitly allowed stable IDs and full provenance/lineage. It sees the
same current state, task contract, event, complete event history, progress,
world state, and compute budget. No information is withheld.

## Registered fixed-model treatment

- Model: `Qwen/Qwen3-32B`.
- Serving: local vLLM OpenAI-compatible chat completions endpoint.
- Sampling: temperature 0, top-p 1, seed 20260904, thinking disabled.
- Budget per event: one call, 4096 output tokens, 90 seconds.
- Model context: 32768 tokens; the preflight verifies that the estimated
  prompt-plus-output request fits even in the primary profile.
- Seeds: 0 through 19.
- Profiles: calibration, lineage_valid, long_lineage.
- Methods: CoPE and FSR-PC.
- Pairing key: `(profile, seed)`; method is excluded.
- Order: CoPE first on even seeds, FSR-PC first on odd seeds.
- Physical controller: the same privileged LIBERO geometry oracle in both arms;
  no learned manipulation policy is used.

## Causal task

The original root workflow produces the registered final assignment:

1. butter to basket B;
2. milk receipt token to basket A;
3. yogurt closure token to basket A.

Nested detours change both the primary destination and the bound continuation.
The deepest detour is constructed so its first action is also butter to basket B
while its receipt/closure actions differ. The final event asks to withdraw every
temporary detour and restore the depth-zero ancestor. Correct task completion
therefore requires the persistent parent/root chain and the root's bound
continuation, not merely the current canonical goal.

## Primary outcome

`task_completion = all_events_processed AND all_generations_valid AND
root_lineage_restored AND compiled_plan_matches_root AND physical_success`.

All attempted episodes remain in the denominator. In particular, timeout,
truncation, malformed JSON, invalid schema, history loss, graph inconsistency,
wrong lineage selection, and controller failure are failures, not exclusions.

Primary inference is the paired completion difference on `long_lineage`, with
rates and Wilson intervals, exact McNemar p-value, and paired bootstrap 95%
interval for CoPE minus FSR-PC.

## Diagnostics

1. Generation validity by method and failure category.
2. Completion among pairs where both arms generated valid states.
3. Per-call prompt/completion tokens and latency.
4. Exact equality of exogenous fingerprints through the first failed call.
5. Exact registered-transition match.
6. Calibration profile parity.
7. Nominal physical-controller gate.

The conditional-valid analysis is never substituted for the primary outcome.

## Gates

1. `run_r3_tests.sh` must pass.
   Its causal task gate must show that a lineage-aware compiler succeeds while
   a surface-only compiler with the same first object-target action fails.
2. Server preflight must list the registered model; a live first-event call for
   both methods must parse and validate.
3. The no-LLM nominal physical gate must achieve at least 8/10. If it fails,
   stop: the manipulation substrate is not reliable enough to test semantics.
4. If the calibration profile has widespread invalid output in both arms, stop
   and treat it as a model/prompt integration failure rather than a method result.
   The executable threshold is at least 80% valid complete episodes in each arm;
   the runner enforces this before starting later profiles.
5. Never tune the primary state size or output budget after inspecting primary
   method outcomes. Any change creates a new protocol version.

Twenty paired seeds were registered before the fixed-model run. With ten or
more discordant pairs all favoring one arm, the two-sided exact McNemar p-value
is at most 0.001953; twenty seeds also leave room for non-discordant controller
or model outcomes while preserving paired analysis.

## Interpretation boundary

The high-state condition deliberately places the explicit full-state document
near or beyond a finite output limit while leaving the same input within model
context. That is part of the systems hypothesis: repeated complete regeneration
has a serialization and reliability cost. The calibration and conditional-valid
analyses distinguish this cost from lineage reasoning errors.
