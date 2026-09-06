# Changelog

## r2 — post-audit revision (2026-08-07)

Response to the independent audit of the first LIBERO/MuJoCo execution
(`cope_fsrpc_v2_execution/`, analysed in `cope_fsrpc_v2_analysis/`). Both of
those folders are immutable evidence and were not modified.

### What the first execution established

- A genuine LIBERO / robosuite 1.4.1 / MuJoCo 2.3.7 run — `backend=libero_mujoco`
  in 70/70 episodes, no fallback to Synthetic2D or a mock executor.
- **Rendering was CPU OSMesa; the host's eight RTX 3090s were idle.** It is a
  CPU-rendered simulator run on a GPU host, not a GPU robotics result. The
  controller is a privileged geometry oracle, not a learned policy.
- CoPE 16/20, FSR-PC 16/20, no-adaptation 0/20.
- **CoPE and FSR-PC had identical physical outcomes** — every behavioural metric
  equal pair by pair, 0 discordant pairs, McNemar p = 1.0.
- Four shared failures were caused by `grasp_not_acquired` on milk.
- That controller failure prevented the restore interruption from being
  delivered in **8 of 30** I2/I4 method episodes.
- 162 candidates were rollout-verified; **zero were rejected**.
- CoPE's demonstrated advantage was **representational/auditability**, not
  behavioural success.

### Root cause fixed in r2

The I2/I4 restore event was keyed on `g_milk` *completing*:

```
if trigger2 in completed_goal_ids:      # backend_episode.py:145-152 (v2)
    deliver(u2)
```

A grasp failure therefore deleted an experimental condition while the episode
still counted as a valid I2/I4 episode.

### Changes

**Added**

- `cope/benchmark/scheduler.py` — pre-registered elapsed-step interruption
  scheduler. `t_restore = t_suspend_actual + delta_steps`. Records
  `scheduled_step`, `actual_delivery_step`, `delivery_delay`,
  `delivery_failure_reason`, and world-state hashes. Undelivered events are
  recorded as `event_not_delivered_due_to_episode_termination`, never omitted.
- `cope/benchmark/failure_layers.py` — deterministic
  infrastructure → adaptation → controller → task hierarchy. **A correct state
  update followed by a failed grasp is a controller failure, never an
  adaptation failure.**
- `cope/benchmark/verifier_probe.py` — verifier-discrimination diagnostic and
  the `CoPE_full` vs `CoPE_no_rollout_verification` comparison.
- `cope/policies/fsrpc_variants.py` — `FSR-PC_stable_ids` and
  `FSR-PC_provenance`. Both still regenerate the complete state; neither may
  apply a CoPE patch (asserted).
- `cope/policies/cope_ablations.py` — `CoPE_no_rollout_verification`.
- Condition **I5** (nested override / restoration) in `basket_task.py`.
- `scripts/cope_r2_dry_run.py`, `tests/test_postaudit_fixes.py` (92 tests).

**Changed**

- `cope/benchmark/backend_episode.py` (the LIBERO path) and
  `cope/benchmark/physical_episode.py` (the CPU path) both deliver on the
  scheduler. Delivery is attempted at leg start, **on the pick-failure branch**,
  mid-leg, and in a final drain.
- `cope/audit_trace.py` — added a **provenance evidence path** so the audit
  score is not defined by CoPE operator names.
- `cope/repair_bridge/goal_compiler.py` — canonical live-target comparison, so
  the two representations compile to the *same* repair goal for the same
  semantic change (found by a test on I5).
- `cope/patch_validator.py` — `suspended → overridden` added to the lifecycle
  table (a suspended goal may be covered by a temporary stand-in). `EXPIRED`
  remains terminal.
- `cope/backends/base.py` — concrete `current_step()`.
- Episodes now also write `interruptions.jsonl` and `candidate_rollouts.jsonl`,
  and report separate denominators.

**Unchanged (per the brief)** — ConstraintState, ConstraintSlot, the typed patch
operators, CoPEPatchPolicy, FSRPCPolicy, continuation capture,
ConstraintStateToRepairGoalCompiler's contract, RepairManager, candidate
synthesis, legality/feasibility filters, RolloutVerifier, TaskProgram splice,
restore/resume semantics. `rekep_repair/` is byte-identical to the pre-pivot
commit.

### New CPU finding (r2 dry run)

Audit coverage decomposes as:

| condition | CoPE | FSR-PC | +stable_ids | +provenance |
|---|---|---|---|---|
| I1 | 1.000 | 0.667 | 0.667 | 1.000 |
| I2 | 1.000 | 0.333 | 0.333 | 1.000 |
| I3 | 1.000 | 0.500 | 0.500 | 1.000 |
| I4 | 1.000 | 0.333 | 0.333 | 1.000 |
| I5 | 1.000 | 0.200 | 0.200 | 0.800 |

**Stable IDs do not close the audit gap; explicit provenance almost entirely
does.** CoPE's audit advantage is therefore attributable to *recording
provenance*, not to local editing per se — except under I5, where a residual
gap remains and lineage is genuinely load-bearing. This weakens the naive
"CoPE has an audit advantage" claim and must be reported that way.

### Not claimed

No behavioural advantage for CoPE is claimed. The r2 changes are experimental
design fixes; they do not by themselves produce any new physical result.
