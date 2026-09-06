# GPU experiment plan

## 1. Single-GPU debugging plan

Work on **GPU 0 only** until Milestone 1 passes. Order:

| # | Goal | Command (all `REMOTE GPU SERVER ONLY`) | Gate |
|---|---|---|---|
| 1 | simulator alive | `run_omni_smoke_test.py --steps 100` | non-zero step rate |
| 2 | ReKep alive | `run_rekep_baseline.py --mode nominal` | task completes as stock |
| 3 | wrapping is transparent | `--mode wrapped` | **identical** stage sequence |
| 4 | one repair works | `--mode repair` | 8 acceptance conditions in the runbook |
| 5 | reproducible | re-run 3 and 4, same seed | stage sequence exact |

Debug one variable at a time. If step 4 misbehaves, first check the horizon
budget, then the adapter keypoint indices, then predicate stability — in that
order, because that is the order of likelihood.

## 2. Multi-GPU scaling plan

Only after the Milestone-1 gate file exists.

```bash
NUM_GPUS=8 TASK=upright_transport MODE=repair SEEDS_PER_GPU=25 \
  bash scripts/launch_gpu_workers.sh
```

* **One OmniGibson instance per GPU.** Do not run two simulators on one 3090.
* Ramp up: 1 → 2 → 4 → 8 workers, checking GPU memory at each step. Renderer
  contention (risk R8) typically appears beyond ~4 concurrent instances.
* Each worker sets `CUDA_VISIBLE_DEVICES` and its own `OMNI_KIT_CACHE_DIR` to
  avoid cross-worker cache lock contention.

## 3. Seed allocation

Seeds are partitioned **disjointly and deterministically** by GPU:

```
gpu g  ->  seeds [ g * SEEDS_PER_GPU , (g+1) * SEEDS_PER_GPU - 1 ]
```

With `SEEDS_PER_GPU=25` and 8 GPUs: seeds 0–199, no overlap.

**Pairing rule:** a given seed must produce the *same scene* for every method.
On CPU this is guaranteed by `sample_scene()` being a pure function of
`(family, condition, severity, seed)` with a process-stable hash. On GPU the
scene must likewise be a deterministic function of the seed — **verify this
explicitly before the sweep**, since paired statistics depend on it.

Run methods **within** a worker (loop over methods inside a seed), not across
workers, so a paired comparison never spans two simulator instances.

## 4. Output-directory convention

```
<OUTPUT_ROOT>/sweep_<timestamp>/
  gpu0/
    configs/worker.json        exact parameters this worker ran
    traces/seed_<N>/trace.json episode trace (stages, events, repairs)
    videos/seed_<N>.mp4        only if video policy says so
    logs/seed_<N>.out|.err     stdout / stderr per episode
    logs/FAILURES              one line per failed seed
  gpu1/ ... gpu7/
  requirements_gpu.txt         copied for provenance
```

Nothing is written outside a worker's own directory, so one crashed worker
cannot corrupt another's results.

## 5. Video policy

Video is expensive and multiplies GPU memory (risk R8).

* **Milestone 1–2:** record **every** episode. You need them to see behavior.
* **Sweeps:** record `seed % 20 == 0` only, plus **every failure**.
* **Paper figures:** re-run the chosen seeds individually with video on.
* Never enable video on all 8 workers simultaneously during a full sweep.

## 6. Failure logging

Every episode writes `.out` and `.err`. A non-zero exit appends to
`logs/FAILURES`. The launcher prints the consolidated failure list at the end
and exits non-zero if any worker failed.

Classify failures before re-running:

| class | signal | action |
|---|---|---|
| infrastructure | Vulkan/OOM/asset errors | fix and re-run the seed |
| ReKep failure | stock task fails | record; it is a baseline property |
| repair failure | fallback engaged, no candidate | **keep it** — this is data |
| harness bug | traceback in our code | fix, then re-run the whole cell |

Do not silently drop failed seeds; a dropped failure biases every rate upward.

## 7. Paired evaluation under physics nondeterminism

This is risk R3, and it is the one most likely to affect the paper.

**Agree the policy before the sweep:**

1. **Determinism probe first.** Run the same seed and method 5 times. Record
   whether the stage sequence is identical and how far continuous quantities
   drift. This probe is cheap and decides everything below.
2. **If the stage sequence is stable** (likely): treat the *discrete* outcome as
   deterministic and use the paired McNemar / bootstrap machinery unchanged,
   with continuous metrics reported as medians with IQR.
3. **If the stage sequence is not stable:** paired binary tests are no longer
   exact. Fall back to: more seeds per cell; report paired *differences* rather
   than absolute rates; and state the nondeterminism explicitly as a limitation.
4. **Never** compare a method run at one time against another run at a different
   time without the same seed *and* the same simulator build.

Record the probe result in the paper's experimental-setup section either way —
it is a fact about the platform that reviewers will ask about.

## 8. Statistical reporting (unchanged from CPU)

Wilson intervals for proportions; paired bootstrap CIs for differences; exact
McNemar for paired binary outcomes; Holm correction across each comparison
family; effect sizes always, not only *p*-values. Report **SD, CFR and TS
separately** — never substitute safe delivery for task success.
