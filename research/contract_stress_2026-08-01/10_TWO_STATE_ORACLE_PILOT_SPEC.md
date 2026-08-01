# Two-state oracle pilot specification — blocked until contract gates pass

Date: 2026-08-01 (Asia/Shanghai)

## Current status

**BLOCKED. Do not run this pilot yet.** Every row in
`08_ACCEPTANCE_MATRIX.csv` must pass on both native full-state output and the
materialized post-CoPE state, and the main FSR path must stop executing provider
controller prose.

## Purpose

This is a smoke test of interface equivalence and execution substrate, not a
statistical method comparison. It asks whether oracle FSR-PC and oracle CoPE
produce equivalently accepted persistent task states from identical events and
whether those states drive the intended task behavior.

## Frozen reserve allocation after unblocking

| Pair | Suite/task/state | Event | Expected accepted directive |
|---|---|---|---|
| `pilot:task01:state25:replace` | LIBERO-10 task 1, state 25 | after exactly one original object is physically in the basket for 5 stable steps, replace the pending sibling with `alphabet_soup_1` | shared compiled updated-goal prompt |
| `pilot:task01:state26:cancel` | LIBERO-10 task 1, state 26 | after exactly one original object is physically in the basket for 5 stable steps, cancel the pending sibling | `HALT` |

States 27–49 remain untouched even if either pilot pair fails.

## Arms

For each pair, independently reset and replay the exact same prefix:

1. Oracle FSR-PC: construct a native canonical full-state-v2 rewrite.
2. Oracle CoPE: select the typed operation with an oracle, apply it atomically,
   materialize the resulting canonical full-state-v2 state.

Both arms then pass through the identical shared validator and compiler. No
learned provider is called, no simulator state is edited by the semantic
operation, and no controller action is emitted while applying the edit.

## Pre-run gates

- 123/123 contract-stress expectations pass after a versioned implementation
  change; no expected-decision edits are allowed.
- Full-state and post-CoPE materialized state use the same schema, validator,
  evidence binding, and compiler.
- `controller_prompt` supplied by either producer is diagnostic-only.
- Formal readiness reports a non-fake simulator-predicate validator with a
  source commit. The oracle pilot may use an oracle producer, but the validation
  adapter itself cannot be a test fake.
- Prefix action digest, pre-patch MuJoCo-state hash, event step, end-effector
  pose, and held-object pose match within each pair.
- Patch application preserves simulator state and emits zero actions.
- Full regression and all corruption/atomicity suites pass.

## Go/No-Go endpoints

The pilot passes only if both arms, in both pairs:

- accept the same event and reject no canonical field;
- materialize semantically identical current goals, commitments, progress,
  plan, entities, and evidence versions;
- compile to identical execution directives;
- preserve the completed original-object milestone;
- execute zero obsolete pending-goal actions after the event;
- replacement pair: physically completes the updated two-object goal within the
  already fixed 280 post-event-action recovery budget;
- cancellation pair: issues no post-event policy action and retains the
  completed object for the fixed hold verification window.

Any mismatch is NO-GO for a learned-provider pilot. A controller substrate
failure is reported as inconclusive for representation and does not authorize
changing the validator or reusing states 25–26 as fresh evidence.

## Learned-provider step after a clean pilot

Only after this pilot passes should the same real model receive byte-identical
recovery inputs and equal decoding budgets for native full rewrite versus typed
patch. The first learned endpoints are output validity, stale-reference rate,
atomicity, progress preservation, latency, tokens, retries, and timeouts—not a
manufactured physical success difference after equivalent states compile to the
same directive.
