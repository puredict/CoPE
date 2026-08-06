# CoPE–FSR-PC end-to-end readiness audit

Date: 2026-08-01

Remote worktree: `/home/lijingsu/codex-worktrees/fsr-pc-v2-canary`

Audited preregistration commit: `e4e923e22880f079a343c1ad450f0e8158b1e819`

## Decision

**NO-GO for a formal CoPE–FSR-PC manipulation comparison.** The repository
contains a useful fairness scaffold, persistent-state engine, semantic
replacement validators, and formal anti-fake guards. It does not yet contain a
real high-level provider, a real revalidation validator, or a shared canonical
compiler path for FSR-PC and CoPE. Running the current comparison would either
be refused by the guards or compare different downstream interfaces.

The fresh oracle substrate result reaches the event in 9/10 assigned states,
which passes the preregistered minimum substrate threshold of 8/10. That does
not remove the semantic/provider blockers below.

## What is genuinely implemented

| Component | Evidence | Status |
|---|---|---|
| Exact common recovery input and provider budget contract | `cope/providers/base.py`, `cope/types.py`, `tests/test_provider_contract.py` | Implemented and unit-tested |
| Six-arm paired runner, anti-fake readiness checks, raw provider-call retention | `experiments/cope_main_comparison.py`, `cope/runner.py`, `cope/validation.py` | Implemented scaffold |
| CoPE typed patch application, lifecycle/authority checks, unaffected-slot preservation | `cope/state_engine_adapter.py`, `cope/engine.py`, semantic tests | Implemented mechanism |
| Strict semantic replacement full-state v2 validator and shared diagnostic compiler | `cope/semantic_replacement.py` | Implemented in the canary path |
| Oracle replacement execution and repeated interruption canaries | `experiments/oracle_*`, committed raw research artifacts | Mechanism evidence only |
| Fresh oracle recovery substrate | `research/fresh_state_recovery_2026-08-01/` | 9/10 assigned states reach event; 1 method-independent pre-event failure |

## Blocking contradictions

### P0 — no real provider adapter

`configs/cope_main_comparison_v1.yaml` leaves `provider.factory`, provider name,
and model null. `cope/providers/` contains only `base.py` and the explicitly
test-only `fake.py`. `experiments/cope_main_comparison.py` refuses rollouts
with `metadata.is_fake=True`, and `cope/runner.py::readiness_report` rejects a
missing or fake formal provider.

Therefore no provider has yet produced either a native full rewrite or a typed
CoPE patch under the formal common-input contract.

### P0 — no real revalidation validator

The config leaves `engine.revalidation_validator_factory` null.
`cope/engine.py::validate_engine(formal=True)` requires a configured validator
with `is_fake=False` and a recorded `validator_commit`. The engine is correctly
designed to fail closed, so formal execution is blocked.

### P0 — FSR-PC and CoPE do not share the same compiler path

`cope/methods/base.py::FullRegenerationMethod` accepts
`FullStateOutput.controller_prompt` and sends it directly to the controller.
`CoPEPatchMethod` instead applies a typed patch and uses the engine's compiled
prompt. Thus provider prose can directly control the FSR arm while the CoPE
arm passes through a versioned compiler. This violates the intended
"representation is the only difference" fairness contract.

The stricter canary implementation in `cope/semantic_replacement.py` already
contains the correct design: `controller_prompt` inside the full state is
diagnostic only, the full state is neutrally validated, and execution uses
`compile_controller_prompt(state)`. That path has not been merged into the
main comparison method.

### P0 — current main runner tests a different event family

`configs/cope_main_comparison_v1.yaml` targets `libero_spatial` object
displacements. `cope/libero_backend.py` physically moves a free joint and
constructs an `object_displacement` recovery input. The current research
hypothesis and successful oracle canaries concern authorized replacement,
cancellation, persistent progress, lifecycle state, and repeated semantic
updates in LIBERO-10 task 1.

A spatial relocalization result cannot substitute for the semantic
replacement kill test.

### P1 — the main FullStateOutput schema is weaker than full-state-v2

`cope/types.py::FullStateOutput.from_mapping` checks that constraints and plan
are lists, IDs are unique, and a controller prompt exists. It does not enforce
the exact `full-state-v2` version, current-goal truth, lifecycle status,
authority, state version, progress ledger, supersession lineage, or plan
continuity. Those checks exist separately in
`cope/semantic_replacement.py::validate_oracle_full_state`.

Without unification, FSR-PC can receive malformed or stale full states that are
not subjected to the same semantic contract used in the canary.

## Required implementation slice before a pilot

1. Replace the main comparison's permissive full-state payload with the
   canonical `full-state-v2` semantic IR already exercised by the canary.
2. Apply a neutral validator to FSR-PC full states and CoPE post-patch states.
   Validation must check authorization, state version, lifecycle, lineage,
   physically valid retained progress, and current-goal atoms.
3. Compile both accepted states through the same deterministic, versioned
   compiler. Provider-supplied controller prose must be logged but ignored for
   execution.
4. Add one real provider adapter implementing both `regenerate` and `patch`
   from the exact same `RecoveryInput`, with equal temperature, token ceilings,
   retries, timeout, and model identity.
5. Add a non-fake simulator-predicate revalidation adapter with a recorded
   source commit. It can be privileged for the oracle-mechanism track, but its
   privilege must be identical across CoPE and FSR-PC.
6. Create a semantic-replacement pair manifest for LIBERO-10 task 1 rather
   than reusing the spatial free-joint disturbance atlas.
7. Run CPU contract/corruption tests first; only then run a 2-state GPU pilot.

## Pilot Go/No-Go

The first end-to-end pilot should contain only two untouched reserve states and
the two mandatory arms, Oracle-FSR-PC and Oracle-CoPE-patch, before any learned
provider run. It is permitted only when:

- the readiness report is clean and `test_only=False`;
- both arms receive byte-identical common recovery inputs;
- both pass the same neutral validator and compiler;
- both reproduce the same pre-event action and MuJoCo-state hashes;
- no direct simulator-state edit is used for recovery;
- the execution substrate reaches the semantic event in both states.

If Oracle-FSR-PC and Oracle-CoPE-patch produce equivalent accepted current
states and identical compiled execution, that is expected. The learned
provider comparison must then focus on generation validity, stale references,
atomicity, progress preservation, latency, and token cost—not manufacture a
physical success gap after the semantic outputs have become equivalent.
