# CoPE / RCSP Canary Plan

This is a design note for the `experiment/cope-canary` worktree. It is not a result report and does not authorize large experiments.

## Scope

Phase A adds a pure constraint-state and typed-patch layer:

- constraint slots with stable identity, lifecycle mode, priority, source, validity, restore, lineage, and local history
- deterministic patch application for Insert, Suspend, Override, Promote, Demote, Inherit, Expire, Revalidate, and Restore
- invariant checks for monotonic history and graph references
- a small LIBERO pick/place object-displacement patch builder for CPU tests

It deliberately does not reimplement:

- episode success / timeout / stop semantics
- observation refresh after simulator mutation
- action-budget accounting
- target-joint selection
- dashboard interactive exclusion

Those remain owned by `libero_experiment_core.py` and related validated callers.

## Phase B Dry Run

`cope_oracle_patch_canary.py` defines a dry-run schema for the first real
canary without loading OpenVLA, LIBERO, MuJoCo, or a dashboard. It produces two
records:

- `reactive_disturbed`
- `cope_oracle_patch_prompt`

The dry-run validator checks:

- strict pair-key equality
- explicit target joint
- fresh-observation marker
- no reset or rollback
- CoPE patch operation sequence
- state invariants
- detector source marked as oracle dry-run
- diagnostic fields marked as not empirical model measurements

This is only a schema and trace correctness gate. It is not a performance
result.

## First Real Canary

`cope_real_canary.py` is the Phase C runner skeleton. By default it is
plan-only and prints the fixed canary configuration. It will only load
OpenVLA/LIBERO and run episodes when invoked with:

```bash
scripts/run_project_env.sh \
  /home/lijingsu/vla/.venv/bin/python cope_real_canary.py \
  --confirm-real-run
```

The runner maps `cope_oracle_patch_prompt` onto the existing
`reactive_disturbed` experiment-core mode and changes only the prompt after a
validated CoPE patch trace. It still uses the existing status, fresh
observation, target-joint, and budget helpers.

Only after CPU tests pass, the smallest real canary should use:

- suite: `libero_spatial`
- task: `0`
- initial state: `0`
- seed: `7`
- checkpoint: `/home/lijingsu/vla/models/openvla-7b-finetuned-libero-spatial`
- target joint: `akita_black_bowl_1_joint0`
- disturbance step: `70`
- dx/dy/dz: `[0.10, 0.05, 0.0]`
- policy budget: `220`
- warmup: `10`

Suggested modes:

- `clean`
- `reactive_disturbed`
- `cope_oracle_patch_prompt`

The first canary should pass or fail primarily on trace correctness:

- target joint explicit
- disturbance event has before/after qpos and applied delta
- fresh observation uses the existing refresh helper
- no reset or rollback
- no extra policy budget
- CoPE patch validates
- old target pose expires
- new current target pose is inserted
- grasp-validity slot is suspended
- task goal and goal pose are inherited
- any Restore is preceded by Revalidate

Task success can be recorded as an outcome, but it should not be the only pass criterion for Phase C.

## Expansion Gate

Do not expand beyond the single canary until:

- CPU tests cover patch invariants and failure cases
- the canary runner records CoPE patch trace in `events.jsonl` and `episode_summary.json`
- interactive/debug records remain excluded from formal summaries
- prompt-only recovery is reported as a baseline, not as a complete CoPE implementation
