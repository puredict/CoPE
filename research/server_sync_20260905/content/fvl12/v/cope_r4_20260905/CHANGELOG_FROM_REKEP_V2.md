# Changelog — from `rekep_repair_交接_v2` to `cope_fsrpc_交接_v1`

## Nature of the change

This is a **pivot in the experiment and the paper framing**, not a rewrite.

| | v2 (ReKep repair) | v1 (CoPE vs FSR-PC) |
|---|---|---|
| primary claim | online repair beats offline precompilation | persistent local patching vs full-state regeneration |
| primary task | ReKep pen-in-holder (GPU) | multi-object basket sorting (reliability-gated) |
| ReKep work | the experiment | **retained as an integration case study only** |
| repair core | the deliverable | **reused unchanged, underneath a new semantic layer** |

## Added

### `cope/` — the CoPE semantic layer (new, 13 modules)

| module | role |
|---|---|
| `constraint_slot.py` | the nine-field slot schema, four lifecycle modes, `revalidate()` |
| `constraint_state.py` | immutable state $S_t$, relation graph $G_t$, fingerprinting, canonical lookup |
| `patch.py` | `OpType`, `PatchOp`, `Patch`, `RegeneratedState`, first-paper subset |
| `patch_operators.py` | the seven operators' side effects, exactly per memo §4 |
| `patch_validator.py` | legality table, pre/post validation, restoration guard |
| `audit_trace.py` | history $H_t$ and the five audit queries, with two evidence paths each |
| `state_store.py` | maintains $S_t$/$G_t$/$H_t$; `compile_active()` is the sole executor interface |
| `recovery_manager.py` | **adapter** onto the existing repair engine; maps, never replaces |
| `naming.py` | canonical slot naming, available to both arms |
| `policies/adaptation_input.py` | the shared, fingerprinted information packet |
| `policies/cope_patch_policy.py` | minimal typed patching |
| `policies/fsrpc_policy.py` | the internally defined regeneration baseline |
| `policies/no_adaptation_policy.py` | control arm |

### `cope/benchmark/` — the reliability-gated benchmark

`basket_task.py`, `mock_executor.py` (+ `ReliabilityGate`), `metrics.py`,
`episode.py` (the shared harness where every fairness control lives).

### Scripts, configs, tests, docs, report

- `scripts/run_cope_pilot.py` — Stages A/B/C with the paired statistics
- `scripts/cope_dry_run.py` — side-by-side traced comparison
- `configs_cope_gpu/{benchmark,pilot,machine}.yaml` — **REMOTE GPU SERVER ONLY**
- `tests/test_cope_semantics.py` (19), `tests/test_cope_fairness.py` (53)
- `docs/{COPE_METHOD,FSRPC_BASELINE_SPEC,BENCHMARK_TASK,FAIR_COMPARISON_PROTOCOL,METRICS,PILOT_EXPERIMENT,COPE_GPU_RUNBOOK,COPE_COLLABORATION_NOTES}.md`
- `report/cope_fsrpc_experiment_design.tex` → compiled PDF (7 pages)

## Changed

Only one file outside `cope/` was touched, and only additively:

- `cope/patch.py::RegeneratedState.to_dict()` now emits the full slot snapshot
  so the audit layer can diff consecutive regenerations. Without it FSR-PC could
  not answer even the queries a snapshot genuinely supports, and the audit
  metric would have been circular.

## Unchanged (verified)

- **The entire `rekep_repair/` repair core.** No file modified. All 94
  pre-existing tests still pass.
- `rekep_repair/benchmark/statistics.py` is reused as-is for the paired
  statistics.
- `rekep_repair/gpu_metrics/` and the GPU P0 fixes from v2 are untouched.

## Immutable evidence, not modified

| folder | role |
|---|---|
| `rekep_gpu_execution/` | original GPU run evidence |
| `rekep_gpu_analysis/` | the read-only audit of it |
| `rekep_repair_交接/` | v1 handoff |
| `rekep_repair_交接_v2/` | v2 handoff (GPU P0 fixes) |

## Test count

| | v2 | v1 |
|---|---|---|
| pre-existing | 94 | 94 (all still pass) |
| CoPE semantics | — | 19 |
| CoPE fairness / benchmark | — | 53 |
| **total** | **94** | **166** |

## What did *not* change conceptually

The repair execution layer's contract is intact: continuation capture, operator
synthesis, legality checking, sequential rollout verification with hard
rejection, splicing, restoration, resumption. CoPE sits above it and supplies
the *semantic* intent (which goal was cancelled, which preserved) that world
predicates cannot express.
