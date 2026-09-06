# GPU Milestone 1 — one nominal + one repaired ReKep episode

> **Every command here is `REMOTE GPU SERVER ONLY`. Nothing below has been
> executed.** The dry-run equivalents were validated on CPU and prove wiring
> only, never GPU behavior.

**This milestone is not an experiment.** It is the go/no-go gate:

> one nominal ReKep episode and one online-repaired ReKep episode execute
> reproducibly on a single RTX 3090 using the same underlying ReKep solvers.

## Step 0 — environment

`REMOTE GPU SERVER ONLY`

```bash
python scripts/check_gpu_environment.py
```

Must print `OK: environment ready.` Then:

```bash
python scripts/run_omni_smoke_test.py --steps 100
```

OmniGibson must open a scene, step, and render **before** ReKep is involved.

## Step 1 — run one official ReKep task UNCHANGED

`REMOTE GPU SERVER ONLY`

```bash
python scripts/run_rekep_baseline.py --mode nominal --task pen_insertion --steps 400 --out runs/milestone1/nominal
```

Use ReKep's **cached** queries so no VLM key is needed. Record: stage
transitions, per-stage constraints, success, wall-clock, seed.

**Acceptance:** the task completes as it does in stock ReKep. If it does not,
stop — nothing downstream is interpretable.

## Step 2 — log stages and constraints

The trace must contain, per step: active stage index, its subgoal and path
constraint identifiers, and the keypoint set. This is the reference the wrapped
run is compared against.

## Step 3 — wrap the fixed stage program in `TaskProgram`

Convert ReKep's `num_stages` + per-stage constraint lists into `StageSpec`s and
build a `TaskProgram`. **No repair yet.** Read the active stage from
`TaskProgram` instead of the integer index.

## Step 4 — parity check (the critical one)

`REMOTE GPU SERVER ONLY`

```bash
python scripts/run_rekep_baseline.py --mode wrapped --task pen_insertion --steps 400 --out runs/milestone1/wrapped
```

**Acceptance:** identical stage sequence and identical success outcome vs
Step 1, on the same seed. Any divergence is a wrapping bug and must be fixed
before proceeding — it would otherwise contaminate every later comparison.

## Step 5 — inject ONE temporary obstacle event

Add a scripted obstacle (a "hand" proxy) that enters the workspace during a
chosen stage and withdraws after N steps. Ground-truth predicate, no VLM: the
CPU study shows detector *delay* barely affects safe delivery, but observation
*noise* dominates — so start with a clean predicate and add noise later.

## Step 6 — execute ONE synthesized repair

`REMOTE GPU SERVER ONLY`

```bash
python scripts/run_rekep_baseline.py --mode repair --task upright_transport --steps 400 --out runs/milestone1/repair
```

**Acceptance — all of:**
1. the event is detected and a continuation is captured;
2. the planner **synthesizes** an operator sequence (not a lookup);
3. the rollout verifier accepts it, calling **ReKep's own** subgoal/path solvers;
4. the graph is spliced: interrupted stage `SUSPENDED`, not `COMPLETED`;
5. repair stages execute;
6. the restore contract validates;
7. the interrupted stage **resumes** and the task completes;
8. `trace.json` + video are written.

The CPU dry-run already produces exactly this program shape:

```
pour → …::r1::suspend#0 → retreat#1 → stabilize#2 → waituntilclear#3
     → realign#4 → resume#5 → pour#resume::r1
```

## Step 7 — reproducibility

Run Steps 4 and 6 twice with the same seed. Traces must match to the sim's
determinism tolerance. **Note:** ReKep's README warns OmniGibson physics can be
non-deterministic even at a fixed seed — so define the tolerance up front
(stage sequence must match exactly; continuous values within tolerance).

## Step 8 — open the gate

Only when Steps 1–7 pass:

```bash
touch runs/milestone1/GATE_PASSED
```

`scripts/launch_gpu_workers.sh` refuses to start a sweep without this file.

## Initial task order

1. **upright object transport** + temporary obstacle intrusion;
2. **pen alignment/insertion** + target relocation;
3. **placement** + object slip;
4. *(later)* compound interruption.

No fluid simulation initially — orientation and relative pose are the pouring
proxy.
