# Oracle second-replacement timing sensitivity

Date: 2026-07-31

Environment: Python 3.10.12, MuJoCo 2.3.7, robosuite 1.4.1,
LIBERO 0.1.0, NumPy 1.26.4; CPU execution with GPU visibility disabled.

> Evidence class: privileged oracle mechanism canary. This is a real
> MuJoCo/LIBERO execution experiment, but it is not a learned-policy or
> end-to-end CoPE evaluation.

## Integrity gates

- Episodes: 30 (15 independently reset pairs).
- Every pair has an identical pre-event low-level action SHA-256.
- Every pair has an identical pre-event MuJoCo state SHA-256.
- EEF and held-object event poses match within their serialized values.
- Every semantic patch emitted zero simulator actions and left the
  MuJoCo state hash unchanged.
- Completed progress was queried from the simulator before each patch;
  it was never asserted unconditionally by the experiment runner.

## Results

| Event timing | Mean event step | Stale updated-goal success | Safe recovery success | Stale object executed | Safe mean steps | Mean overhead | Min horizon margin |
|---|---:|---:|---:|---:|---:|---:|---:|
| post_lift | 286.8 | 0/5 | 5/5 | 5/5 | 529.6 | 146.0 | 63 |
| mid_transfer | 305.8 | 0/5 | 5/5 | 5/5 | 561.6 | 174.4 | 31 |
| pre_release | 321.6 | 0/5 | 3/5 | 5/5 | 595.2 | 209.6 | -7 |

Safe-return position error: mean 1.66 mm; maximum 2.45 mm.

## Observed late-recovery boundary

At pre-release, the updated physical goal was reached in 5/5 trials, while the full 600-step recovery gate passed in 3/5. 2 trials crossed the horizon.

Because every patch integrity gate passes before recovery begins,
late failures are attributable to the cost of exact return-and-switch,
not to rejection of the persistent commitment edit. This motivates a
bounded local staging/drop operator or direct redirection when valid,
rather than always returning the obsolete object to its original pose.

## Interpretation boundary

The canary isolates one mechanism: after a commitment changes while
an obsolete object is held, a persistent semantic patch alone does not
stop the running skill. Explicit return-and-switch repair is required.
The experiment uses oracle object identity, oracle event timing, oracle
operation selection, privileged geometry, and a custom simulator-predicate
goal because the original LIBERO BDDL goal still names butter.

The reported safety evidence is limited to grasp retention, release,
return-position error, target predicates, and the 600-step horizon.
Force, contact impulse, collision severity, and human safety are not
measured and must not be inferred from these rows.

The five states, when all are present, are LIBERO's five official initial
layouts; they are not independent random seeds. This small canary is for
mechanism qualification, not a powered headline comparison.

## Reproduction

GPU inference is not used. Run with `CUDA_VISIBLE_DEVICES=""`
and the repository's existing LIBERO environment:

```bash
export HF_HOME=/home/lijingsu/vla/cache/huggingface
export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=""
scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  experiments/oracle_interruption_timing_gate.py \
  --state-id 0 --timing post_lift --mode safe_return_switch \
  --output-csv /new/non_overwriting/path.csv
```

Repeat states `0..4`, timings `post_lift`, `mid_transfer`, and
`pre_release`, and both modes. Then run the strict summarizer.
