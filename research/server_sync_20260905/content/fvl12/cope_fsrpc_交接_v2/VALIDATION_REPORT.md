# Validation report

Validation date: 2026-08-04 (Asia/Shanghai).

This report separates inherited CPU evidence from the new LIBERO/MuJoCo
evidence. A passing CPU result is never counted as a real-simulator result.

## 1. Package intake and regression checks

| check | result |
|---|---|
| supplied ZIP `SHA256SUMS.txt` | all entries passed before modification |
| complete handoff root, not only `code/` | confirmed |
| immutable CPU snapshot | SHA-256 `607704af05fd2fa1ccadcde9a3317fb0fefa113ab82312bf3515c154b8ee7418` |
| packaged tests before backend work | 135 passed |
| packaged tests after backend work | **138 passed** |
| CPU `cope_pipeline_trace.py --all --seed 0` | **PASS**, both arms, I1--I4 |
| explicit unknown/unavailable backend failure | tested; no silent fallback |

The old ReKep worktrees, prior result directories, and the supplied ZIP were
not modified. Every new remote experiment used a fresh versioned directory.

## 2. Server audit

| component | observed value |
|---|---|
| host | `fvl12`, Ubuntu 22.04.5, kernel 5.19.0-50 |
| project revision | `/home/lijingsu/vla`, `570d78333ee977c8ae6de3d97120b23272c4c660` |
| simulator | LIBERO source + robosuite 1.4.1 + MuJoCo 2.3.7 |
| robot/controller | OnTheGroundPanda / OSC_POSE / 20 Hz |
| renderer | OSMesa CPU offscreen, 128 x 128 `agentview` |
| GPU inventory | 8 x RTX 3090 24 GiB; idle at audited launches |
| learned checkpoint/CUDA inference | none |

The project-isolated Python environment and source tree were reused without
sudo, Docker, a new account, or process termination. Existing untracked server
directories were left untouched.

## 3. Task and native-state preflight

The custom BDDL loaded all six physical objects (three items and three basket
targets) and all three contain regions. A direct nominal probe placed all three
items successfully and satisfied 3/3 task predicates in 599 simulator steps.

Native MuJoCo state capture/change/restore was checked before the repair
preflight. `sim.forward()` introduced only a `1.11e-16` quaternion
renormalization; `data.ctrl`, mocap state, and OSC controller state restored
exactly. The canonical experiment hash therefore rounds continuous arrays to
12 decimal places and normalizes signed zero. Geometric task, collision,
attachment, and continuation tolerances were not loosened.

## 4. Candidate-isolation preflight

Passing final artifact root: `preflight_20260804_v5`.

| candidate | real rollout observation | decision | restore |
|---|---|---|---|
| 0 | 27 MuJoCo contacts, including 1 protected-object contact | reject: collision | same checkpoint hash |
| 1 | continuation handoff error about 0.142 m | reject: invalid handoff | same checkpoint hash |
| 2 | attachment retained; handoff error about 0.0013 m | accept | same checkpoint hash |

The preflight also passed actual pick, actual place, revised task predicate,
and MP4 writing checks. Earlier diagnostic roots `v1`--`v3` are preserved and
not counted as passing runs. `v4` passed the prior hash; `v5` repeated the full
test after the hash was strengthened to cover held-object state, target-return
poses, collision bookkeeping, and video/contact/log cursors.

## 5. Full-episode debug validation

| run | result | important evidence |
|---|---|---|
| nominal seed 0, no adaptation | pass | 3/3 predicates, collision false, 599 steps, 600 video frames |
| I1 seed 0, CoPE | pass | 3 candidates, full ten-marker pipeline, splice, restore, resume, 601 steps |

The valid I1 artifact is `debug_I1_cope_seed0_v3`. It cancelled yogurt before
placement and redirected butter from basket B to basket A. The selected repair
was `Suspend + Stabilize + UpdateTargetContract + Realign + Resume`; continuation
handoff error was about 0.00082 m. All candidate branches began from and
returned to the same checkpoint hash.

An earlier I1 attempt is excluded because a raw (noncanonical) hash compared
the `1.11e-16` normalization bit. Another completed its pipeline but lost the
SSH output channel during execution; because the episode did not finish and
write all artifacts, its denominator is invalid. The runner now catches
`BrokenPipeError` in verbose logging so transport cannot affect control.

## 6. Reliability gate and paired pilot

The real reliability gate is exactly ten nominal `no_adaptation` episodes.
Passing requires 10 valid episodes and at least 8 task successes. The 60-run
pilot is not launched until both this gate and the manual debug checks pass.

Final gate and pilot rows are written here only after completion; pending work
is never reported as a result.

## 7. Required per-episode evidence

Every real episode directory contains:

1. `result.json`;
2. `events.jsonl`;
3. `adaptation_trace.jsonl`;
4. `repair_trace.jsonl`;
5. `state_snapshots.json`;
6. `simulator.log`;
7. `video.mp4`.

The experiment summary reports attempted and valid episode/candidate
denominators separately. Infrastructure failures never enter the scientific
numerator as task failures or successes.

## 8. Claim boundary

These checks support a real LIBERO/MuJoCo mechanism integration with a
privileged geometry oracle. They do not support claims about physical robots,
learned-policy robustness, GPU inference, calibrated safety, or contact force.
The synthetic CPU pilot remains useful for regression and semantic fairness,
but its success rates are not evidence about this simulator gate.
