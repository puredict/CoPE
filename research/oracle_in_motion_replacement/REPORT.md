# Lift-time second replacement and executable recovery

Date: 2026-07-31

Branch: `codex/fsr-pc-v2-canary`

## Question

What happens when a second semantic replacement arrives after the currently
active object has already been grasped and lifted?

Physical and semantic sequence:

1. place cream cheese in the basket;
2. patch butter to alphabet soup;
3. pick and lift alphabet soup by about 0.20 m;
4. patch alphabet soup to tomato sauce;
5. either continue the stale held-object skill, or execute a safe
   return-and-switch repair.

Both treatment arms receive the same accepted two-patch persistent state.
They differ only in executable repair.

## Results

| Gate | Stale continuation | Safe return-and-switch |
|---|---:|---:|
| Lift checkpoint captured | 5/5 | 5/5 |
| Second patch accepted | 5/5 | 5/5 |
| Hash chain valid | 5/5 | 5/5 |
| Updated goal success | 0/5 | 5/5 |
| Stale alphabet soup executed | 5/5 | 0/5 |
| Valid cream-cheese progress retained | 5/5 | 5/5 |
| Within 600-step horizon | 5/5 | 5/5 |

Safe return verification passed in
5/5 trials, and the tomato-sauce
replacement skill passed in 5/5.
Return-position error averaged 1.64
mm and was at most 2.46 mm.

The paired updated-goal effect is +100 percentage points (5/5 versus 0/5).
With five pairs, the two-sided exact sign/McNemar p-value is 0.0625.

## Recovery cost

- event-two lift checkpoint: mean step
  286.8;
- stale continuation terminal: mean
  383.6 steps;
- safe return-and-switch terminal: mean
  529.6 steps;
- conservative recovery overhead: 146.0 steps;
- safe arm range: 517–537 steps;
- worst remaining horizon margin: 63 steps.

The recovery succeeds, but the overhead is material.  A nearby certified
staging region could be more efficient than returning the object to its
exact initial pose.

## Main interpretation

The typed commitment patch is necessary but not sufficient.  In the stale
arm, the persistent state is correct (`alphabet_soup` is overridden and
`tomato_sauce` is active), yet the already-running skill still places
alphabet soup in the basket in 5/5 trials.  Only checkpoint-aware executable
repair prevents stale execution.

This supplies direct evidence for the intended two-layer architecture:

`CoPE semantic edit -> repair goal -> safe old-object disposition -> new skill`

It also argues against evaluating CoPE only by changing an instruction
string: controller continuation state must be captured and explicitly
spliced or terminated.

## Scope and limitations

- Object/region and patch choices are oracle; no provider or learned policy
  is called.
- Checkpoint timing is a deterministic post-lift boundary, not asynchronous
  perception latency.
- Safe return uses privileged start geometry.
- The experiment handles object replacement.  Target replacement while
  holding the same object may admit direct redirection and should be tested
  separately after an insertion-capable caddy skill is qualified.

## Reproduction

```bash
export HF_HOME=/home/lijingsu/vla/cache/huggingface
export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=""

scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  experiments/oracle_in_motion_replacement_gate.py \
  --state-id 0 \
  --mode double_patch_safe_return_switch \
  --output-csv research/oracle_in_motion_replacement/reproduction.csv
```

Primary table: `research/oracle_in_motion_replacement/all_episodes.csv`.

## Next engineering gate

Represent the repair strategy as an explicit compiled repair program rather
than mode-specific experiment control flow.  Compare exact return against a
certified staging-region operator, and add an ablation that applies the
semantic patch but omits checkpoint invalidation.
