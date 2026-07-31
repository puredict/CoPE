# Repeated semantic replacement gate

Date: 2026-07-31

Branch: `codex/fsr-pc-v2-canary`

## Question

Can one persistent CoPE state accept two authorized semantic replacements
without rebuilding the task, while preserving completed progress and
suppressing both stale commitments?

The predeclared chain is:

`butter_1 -> alphabet_soup_1 -> tomato_sauce_1`

`cream_cheese_1` is physically completed before the events and must remain
valid throughout.

## Results

| Arm | Intended terminal | Goal success | Stale execution |
|---|---|---:|---:|
| Original | cream + butter | 5/5 | butter 5/5 |
| Single patch | cream + alphabet soup | 5/5 | butter 0/5 |
| Two events, no edits | cream + tomato sauce | 0/5 | butter 5/5 |
| First patch only; second ignored | cream + tomato sauce | 0/5 | alphabet soup 5/5 |
| Two CoPE patches | cream + tomato sauce | 5/5 | butter 0/5; alphabet soup 0/5 |

All 25 first skills and all 25 selected second skills succeeded.  Valid
cream-cheese progress was retained in 5/5
double-patch trials.  Both typed patches were accepted in
5/5 trials, and their adjacent
hashes formed a continuous chain in 5/5.

The strongest paired comparison holds the first patch fixed:

- ignore event 2: updated goal 0/5; alphabet soup incorrectly executed 5/5;
- apply event 2: updated goal 5/5; alphabet soup executed 0/5.

This is a +100 percentage-point paired canary effect.  With five pairs, the
two-sided exact sign/McNemar p-value is 0.0625; it is not yet a
publication-scale sample.

Mean environment steps:

- original: 316.2;
- single patch: 383.6;
- second event ignored: 383.6;
- double patch: 366.6.

## Persistent-state evidence

Every two-patch treatment followed revision `1 -> 2 -> 3`.  The second
patch's before-hash exactly equals the first patch's after-hash.  Final slot
modes and lineage are:

- butter: `overridden`;
- alphabet soup: `overridden`;
- tomato sauce: `active`;
- cream cheese: `active`;
- lineage:
  `butter -> alphabet_soup -> tomato_sauce`.

Negative unit tests reject stale expected revisions, targeting a non-tip
commitment, reusing an earlier chain object, and claiming physically false
completed progress.

## Scope and limitation

This isolates persistent semantic state and explicit skill selection.
`oracle_operation_selection=True`, `provider_called=False`, and no learned
policy is involved.

Both events occur after the first object is completed and before the next
pick-place skill begins.  The experiment does **not** yet test a second
interruption during an executing motion.  That requires splitting
`pick_and_place` into resumable `pick`, `transport`, and `place` checkpoints
and verifying safe capture/resume.

## Reproduction

```bash
export HF_HOME=/home/lijingsu/vla/cache/huggingface
export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=""

scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  experiments/oracle_repeated_replacement_gate.py \
  --state-id 0 \
  --mode double_patch \
  --output-csv research/oracle_repeated_replacement/reproduction.csv
```

Repeat states `0..4` and modes `original`, `single_patch`,
`double_event_no_edit`, `second_event_no_edit`, and `double_patch`.

Primary table: `research/oracle_repeated_replacement/all_episodes.csv`.

## Next gate

Refactor the qualified controller into resumable skill phases.  Trigger the
second event after object lift, capture the physical checkpoint, apply the
second patch, and verify that the robot redirects the already-grasped object
or safely returns it before executing the new commitment.
