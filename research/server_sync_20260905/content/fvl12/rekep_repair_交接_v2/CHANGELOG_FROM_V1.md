# CHANGELOG — v1 → v2

This folder is **self-contained**. Nothing needs to be merged from
`rekep_repair_交接/` by hand. The v1 handoff, `rekep_gpu_execution/` and
`rekep_gpu_analysis/` are untouched and remain valid as historical evidence.

**Scope of v2: GPU-side only.** The frozen CPU architecture, benchmark, claims
and tests are unchanged — all 71 original CPU tests still pass, byte-identical
behaviour. v2 adds P0-1..P0-4 in a *new* `rekep_repair/gpu_metrics/` package plus
new scripts. No existing CPU module was modified.

---

## Why: what the GPU audit found

| Defect (v1) | Evidence | Fixed by |
|---|---|---|
| No task-success metric — `completed:true` only meant "graph finished + video saved" | nominal runs end pen–holder xy ≈ 0.030 m with the pen visibly inserted; repaired seeds 0/3/5 end 0.094–0.096 m away, seed 7 ends with the pen flat on the table (89.5° from vertical, below the rim) | **P0-1** |
| No candidate rollout — `Scorer` ran with `rollout=None`, `note:"no-rollout"`, score `0.3×5 = 1.5` identically for all 3 candidates; `rejected: []` in 8/8 | all 8 `repaired_result.json` | **P0-2** |
| Restore gate tautological — `lambda: self._native_solver_verified`, flag set `True` immediately before the gate | `run_repaired_rekep_headless.py` lines 211–213 vs 356 | **P0-3** |
| No baseline — nothing to compare against | complete artifact inventory | **P0-4** |
| Only a final JSON — a killed episode (seed 7) left no repair evidence at all | `gpu_7/seed_7/` has a log but no result | **structured logging** |
| Disturbance constant by construction — `linspace(num=5)` + threshold 0.05 forced `displacement=0.075`, `severity=0.5` in every episode | `run_repaired_rekep_headless.py` lines 160–178 | **P0-4** (`pilot_spec`) |

## New files

| File | Purpose |
|---|---|
| `code/rekep_repair/gpu_metrics/geometry.py` | quaternion/axis/containment helpers (numpy only) |
| `code/rekep_repair/gpu_metrics/pen_in_holder.py` | **P0-1** geometric success evaluator |
| `code/rekep_repair/gpu_metrics/gpu_rollout.py` | **P0-2** candidate verifier + enforced state isolation |
| `code/rekep_repair/gpu_metrics/restore_contract.py` | **P0-3** continuation-specific restore contract |
| `code/rekep_repair/gpu_metrics/pilot_spec.py` | **P0-4** paired disturbance spec, 3 method arms |
| `code/rekep_repair/gpu_metrics/structured_log.py` | live JSONL event log (14 event types) |
| `code/scripts/run_gpu_pilot_episode.py` | v2 episode runner (`--dry-run` capable) |
| `code/scripts/run_gpu_pilot.sh` | 20-episode single-GPU pilot with a pre-flight gate |
| `code/scripts/aggregate_pilot.py` | pilot result schema aggregator |
| `code/scripts/evaluate_pen_in_holder_retrospective.py` | applies P0-1 to v1 episodes |
| `code/tests/test_gpu_metrics.py` | 23 tests covering the 12 required cases |
| `code/docs/GPU_SUCCESS_METRIC.md` | metric spec + threshold calibration |
| `code/docs/GPU_V2_INTEGRATION.md` | exact GPU call sites |

**Modified: none.** Every v1 file is byte-identical except that `code/` was
refreshed from the canonical repo (which itself only gained the new files).

## Migration

1. Use this folder instead of `rekep_repair_交接/`. Do not merge.
2. On the GPU host, complete the four call sites in
   `code/docs/GPU_V2_INTEGRATION.md` (build `OmniShadowHost`, insert the
   verifier, install the contract, record the state the metric needs).
3. **Measure the real asset geometry once** and replace `DEFAULT_PEN` /
   `DEFAULT_HOLDER` in `run_gpu_pilot_episode.py` — the defaults are declared
   placeholders and will otherwise silently mis-score every episode.
4. Run the debug episodes, then `scripts/run_gpu_pilot.sh` (20 episodes).
5. Aggregate with `scripts/aggregate_pilot.py`.

## Which v1 GPU claims survive

**Still valid (unaffected by these fixes):**

* Stock ReKep + OmniGibson ran on 8× RTX 3090; ReKep was **subclassed, not
  modified**; its subgoal/path/IK/OSC/constraint code was reused.
* `TaskProgram` wrapped a real ReKep stage program and preserved `1→2→3`.
* Event detection, continuation capture, operator **synthesis**, graph splice
  with correctly namespaced IDs, and stage resumption all executed for real.
* 8-GPU isolation worked; 70/70 checksums verify; 13 videos are readable.
* Seed 7's failure was an **OmniGibson OSC singular Jacobian** reached through
  stock ReKep — a simulator/controller failure, not a method failure.

**Invalidated / must not be repeated:**

* ~~"All eight passed the restore gate"~~ — tautological; carries no information.
* ~~"All eight passed native rollout verification"~~ — that was a shape/finiteness
  check on one already-selected candidate, not a rollout.
* ~~Any implication that `completed: true` means task success~~ — it does not.
* ~~"event displacement 0.075 m in every episode" as an observation~~ — it was
  forced by the interpolation/threshold arithmetic.
* Candidate scoring was **not** state-dependent (`no-rollout`, all scores 1.5).

**Newly surfaced from the audit (worth keeping):**

* `single_gpu/online_repair/repaired_result_run2.json` ends at xy = 0.02945
  against a holder relocated to y = 0.0008 — essentially identical to the
  nominal 0.02947. This is the **strongest existing positive evidence** that
  online repair can achieve the task, and it was buried in v1's reporting.
* `repaired_result.json` and `repaired_result_run1.json` are byte-identical
  duplicates (same SHA-256), so v1's "two repair runs" are really one distinct
  run plus a copy, plus `repaired_result_run2.json`.
* All five `single_gpu/*.mp4` are now unambiguously attributed via
  `log_start + wall_seconds ≈ video timestamp` (±2 s): 19-39-14 = official
  nominal, 19-45-05 = wrapped 1, 20-01-01 = repair 1, 20-08-31 = repair 2,
  20-13-24 = wrapped 2.

## Still requires remote GPU execution

Everything in `gpu_metrics` is CPU-tested against synthetic and fake-host inputs.
**No part of the GPU path has been executed.** Specifically unproven on hardware:
`og.sim.dump_state`/`load_state` round-tripping cleanly enough for candidate
isolation; the cost of one shadow rollout per candidate; the true asset
geometry; and whether the restore contract's tolerances are reachable in
practice.
