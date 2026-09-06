# Project status

Date: 2026-08-07 · Revision: **r2 (post-audit)** · Phase: **CPU complete, LIBERO re-run pending**

## 1. What the first LIBERO/MuJoCo execution established

- Genuine LIBERO / robosuite 1.4.1 / MuJoCo 2.3.7 execution, `backend=libero_mujoco`
  in 70/70 episodes; no fallback to Synthetic2D or a mock executor.
- **CPU OSMesa rendering. The host's eight RTX 3090s were idle.** Not a GPU
  result. Controller is a privileged geometry oracle, not a learned policy.
- **CoPE 16/20, FSR-PC 16/20, no-adaptation 0/20.**
- **CoPE and FSR-PC produced identical physical outcomes** — every behavioural
  metric equal pair by pair; 0 discordant pairs; McNemar p = 1.0.
- Four shared failures were caused by `grasp_not_acquired` on milk.
- That controller failure prevented the restore interruption from being
  delivered in **8 of 30** I2/I4 method episodes.
- 162 candidates rollout-verified, **0 rejected** — the verifier ran but was not
  shown to change any decision.
- **CoPE's demonstrated advantage was representational/auditability, not
  behavioural success.**

## 2. What r2 changes

r2 fixes the experimental design; it produces no new physical result by itself.

| defect | fix |
|---|---|
| restore event coupled to `g_milk` completing | pre-registered elapsed-step scheduler (`cope/benchmark/scheduler.py`) |
| grasp failure silently deleted a condition | delivery attempted at leg start, on the pick-failure branch, mid-leg, and in a final drain; undelivered events recorded explicitly |
| one success flag conflated three layers | deterministic infrastructure → adaptation → controller → task hierarchy |
| verifier never shown to matter | verifier probe + `CoPE_no_rollout_verification` ablation |
| audit advantage not decomposed | `FSR-PC_stable_ids`, `FSR-PC_provenance`, and a provenance evidence path in the audit scorer |
| no lineage-sensitive condition | **I5** nested override / restoration |

## 3. New CPU finding that weakens a previous claim

| condition | CoPE | FSR-PC | +stable_ids | +provenance |
|---|---|---|---|---|
| I1 | 1.000 | 0.667 | 0.667 | 1.000 |
| I2 | 1.000 | 0.333 | 0.333 | 1.000 |
| I3 | 1.000 | 0.500 | 0.500 | 1.000 |
| I4 | 1.000 | 0.333 | 0.333 | 1.000 |
| I5 | 1.000 | 0.200 | 0.200 | 0.800 |

**Stable IDs do not close the audit gap. Explicit provenance almost entirely
does.** So the audit advantage is attributable to *recording provenance*, not
to persistent local editing — except in I5, where a residual gap remains.

## 4. Status

| item | status |
|---|---|
| CoPE core method | **unchanged** (per the brief) |
| `rekep_repair/` frozen core | byte-identical to the pre-pivot commit |
| Scheduler, failure layers, I5, FSR-PC variants, verifier probe | complete |
| CPU tests | **321 passing** (229 prior + 92 new) |
| CPU dry run | 150/150 scheduled events delivered, 0 short |
| LIBERO re-run (r2) | **not started — server required** |

## 5. Claim boundary

No behavioural advantage for CoPE over FSR-PC is claimed. The first execution
found none, and r2 has not re-run on the simulator. Any future claim requires
the r2 LIBERO execution.
