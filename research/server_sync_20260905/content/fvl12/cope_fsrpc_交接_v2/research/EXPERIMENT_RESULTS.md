# Real-simulator experiment results

Date: 2026-08-04. Backend: `libero_mujoco`.

## Evidence policy

Only completed runs with all required artifacts and no infrastructure error
enter valid denominators. Failed diagnostics are retained under distinct
versioned paths. CPU/Synthetic2D outcomes are never promoted to this table.

## Completed checks

| stage | artifact root | attempted | valid | task success | status |
|---|---|---:|---:|---:|---|
| native/custom-task nominal probe | server audit log | 1 | 1 | 1 | pass |
| backend preflight | `preflight_20260804_v5` | 1 | 1 | 1 | pass |
| full nominal debug | `debug_nominal_seed0_v1` | 1 | 1 | 1 | pass |
| CoPE I1 debug | `debug_I1_cope_seed0_v3` | 1 | 1 | 1 | pass |

Nominal probe and full nominal debug each completed all three revised task
predicates in 599 simulator steps. The full nominal episode wrote the seven
required artifacts and a 600-frame video.

The valid I1 CoPE episode completed in 601 steps with no collision. It produced
three checkpoint-isolated candidate rollouts, selected a repair without safe
fallback, spliced the program, validated restoration, resumed the stage,
cancelled yogurt, and redirected butter to basket A.

## Candidate preflight

| candidate | collision | attachment | handoff error | outcome |
|---:|---|---|---:|---|
| 0 | protected-object collision observed | not decisive | n/a | hard reject |
| 1 | no hard collision | retained | approximately 0.142 m | hard reject |
| 2 | no hard collision | retained | approximately 0.0013 m | accept |

All three candidates began at and restored to the same canonical checkpoint
hash. The strengthened hash includes simulator/controller state,
held-object checkpoint, target-return poses, collision bookkeeping, and
artifact cursors. This is a real MuJoCo rollout result, not a mocked validator
decision.

## Reliability gate

The gate consists of exactly ten nominal `no_adaptation` episodes and passes
only with ten valid episodes and at least eight successes. Its final row is
added after the detached server command exits and `stage_a_nominal_gate.json`
is checked.

## Fixed paired pilot

After a passing gate and manual debug, the fixed pilot is exactly:

    5 seeds x 4 conditions x 3 methods = 60 episodes

Methods are CoPE, the internally defined FSR-PC baseline, and
`no_adaptation`. No ablation, extra seed, or sweep is included. The final
summary will report attempted and valid episodes/candidates separately, plus
per-condition task success and paired CoPE--FSR-PC metrics.

## Interpretation boundary

These results test the repair mechanism in LIBERO/MuJoCo with a privileged
geometry oracle. They do not establish learned-policy robustness, physical
robot performance, GPU inference performance, calibrated safety, or a CoPE
task-success advantage. Structural differences in identity, edit locality,
and auditability remain the primary scientific target; behavioural differences
must be reported as measured, including ties or failures.
