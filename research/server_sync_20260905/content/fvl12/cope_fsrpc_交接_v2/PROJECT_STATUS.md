# Project status

Date: 2026-08-04 · Phase: **real-simulator integration validated; gated pilot in progress**

## 1. What is implemented

The original CoPE hypothesis and the frozen repair core are unchanged. The
new work supplies the platform layer that the CPU handoff intentionally lacked:

    event -> CoPE patch / FSR-PC regeneration -> frozen repair engine
          -> checkpoint-isolated candidate rollout in MuJoCo
          -> hard rejection -> splice -> nontrivial restore -> resume

`SimulatorRepairBackend` keeps all simulator-, robot-, controller-, asset-,
checkpoint-, contact-, video-, and task-metric logic outside the CoPE and
FSR-PC method implementations. `Synthetic2DBackend` remains available; the
real path is selected explicitly as `libero_mujoco` and never silently falls
back to the synthetic environment.

| item | status |
|---|---|
| CoPE semantic layer and FSR-PC baseline | preserved |
| Frozen online-repair core | preserved and reused |
| Backend-neutral simulator contract | implemented |
| LIBERO/robosuite/MuJoCo adapter | implemented |
| Real candidate rollout and checkpoint isolation | preflight pass |
| Real revised-task success predicates | implemented |
| I1--I4 physical world-event mapping | implemented |
| Per-episode JSONL/JSON/log/video artifacts | implemented |
| CPU regression suite | **138 passed** |
| Real nominal debug seed 0 | **pass, 3/3 predicates, 599 steps** |
| Real I1 CoPE debug seed 0 | **pass, complete repair pipeline** |
| Real 10-seed nominal gate | running; result is not inferred |
| Fixed 60-episode paired pilot | blocked on the gate by design |

## 2. Audited execution substrate

- Server `fvl12`, Ubuntu 22.04.5; project source at `/home/lijingsu/vla`,
  commit `570d78333ee977c8ae6de3d97120b23272c4c660`.
- LIBERO source, robosuite 1.4.1, MuJoCo 2.3.7.
- OnTheGroundPanda with `OSC_POSE` at 20 Hz.
- Three physical objects and three physical baskets from the installed asset
  library. Abstract `yogurt` is explicitly mapped to `cream_cheese_1`.
- Privileged simulator-geometry oracle for pick/place and repair controls.
- 128 x 128 offscreen video through OSMesa on CPU.

The host has eight RTX 3090 GPUs, but this experiment loads no learned model
and performs no CUDA inference. `nvidia-smi` was checked before launches and
all GPUs were idle; the honest label is a **real simulator mechanism
experiment on a GPU host**, not a GPU-policy experiment.

## 3. Completed real-simulator evidence

The passing preflight (`preflight_20260804_v4`) demonstrated all three
candidate outcomes from the same checkpoint:

- candidate 0 made a real protected-object contact and was hard-rejected;
- candidate 1 was rejected at about 0.142 m continuation handoff error;
- candidate 2 retained attachment and was accepted at about 0.0013 m handoff
  error;
- every branch restored to the same canonical checkpoint hash.

The passing I1 debug (`debug_I1_cope_seed0_v3`) executed three real candidate
rollouts, selected and spliced a repair, validated a nontrivial continuation
handoff, resumed the interrupted stage, cancelled yogurt, and redirected butter
to basket A. It completed successfully in 601 simulator steps without a
collision or safe fallback.

Failed diagnostic attempts are preserved and excluded from valid denominators.
One exposed MuJoCo quaternion renormalization at `1.11e-16`; the state hash now
uses documented 12-decimal canonicalization while the actual state, controller,
`ctrl`, and mocap restore checks remain explicit. Another was invalidated by an
SSH broken pipe; logging is now isolated from the experimental control path.

## 4. Claim boundary

Established: backend integration, real MuJoCo execution, physical world edits,
checkpoint-isolated candidate verification, nontrivial restoration, task
predicates, structured artifacts, and the completed debug episodes above.

Not established: physical-robot performance, learned-policy robustness, GPU
inference performance, calibrated force/safety, or a behavioural advantage for
CoPE. The previous CPU pilot found structural differences in identity,
locality, and auditability, while final task success was tied; those CPU numbers
remain labelled separately from the real-simulator results.

## 5. Gated next step

The real 10-seed nominal reliability gate must have 10 valid episodes and at
least 8 successes. Only after it passes are the fixed 5 seeds x 4 interruption
conditions x 3 methods = 60 episodes launched. No ablation or larger sweep is
part of this handoff.
