# Oracle Skill Controller qualification and CoPE replacement gate

Date: 2026-07-31

Branch: `codex/fsr-pc-v2-canary`

Input base before this experiment: `2fced05`

## Decision

Use the explicit, privileged `LiberoOracleSkillController` as the **mechanism
qualification / execution-upper-bound substrate** for CoPE.  It removes the
30% clean-success ceiling that made ReKep/OpenVLA-style end-to-end results
ambiguous.  Do **not** present it as a learned-policy baseline or as evidence
that event interpretation is solved: object/region selection is oracle, no
provider is called, and simulator geometry is privileged.

Keep learned OpenVLA results as a separate realism stratum.  Do not average
learned-controller and oracle-controller trials into one headline number.

## Results

| Gate | Result | Interpretation |
|---|---:|---|
| Task 0 clean original, full task | 5/5 | clean execution ceiling |
| Task 0 atomic pick-place skills | 10/10 | two objects per state |
| Task 1 clean original | 5/5 | cream cheese + butter |
| Updated goal from reset | 5/5 | reachability upper bound |
| Checkpoint no edit, updated goal | 0/5 | stale-resumption control |
| Checkpoint Oracle CoPE patch | 5/5 | typed `Override` treatment |
| Patch accepted by CoPE engine | 5/5 | real state-engine transition |
| Valid progress retained, patch arm | 5/5 | cream cheese preserved |
| Stale butter executed, no-edit | 5/5 | expected failure mechanism |
| Stale butter executed, patch arm | 0/5 | successful suppression |

The paired checkpoint effect is +100 percentage points (5/5 versus 0/5).
With only five pairs, the exact two-sided sign/McNemar p-value is 0.0625, so
this is a passed canary, not a publication-scale statistical claim.  The
95% exact binomial intervals are wide (approximately 47.8–100% for 5/5 and
0–52.2% for 0/5).

Mean environment steps were 319.2
for clean original, 387.6 for the
replacement patch arm, and 318.2 for Task
0 clean original.  Every run stayed below LIBERO's 600-step episode horizon.

`libero_task_success=False` in updated-goal arms is expected: the immutable
BDDL terminal still encodes the old butter goal.  Updated-goal success is
therefore scored from the ground-truth conjunction
`In(cream_cheese_1, basket_region) AND In(alphabet_soup_1, basket_region)`.

## Typed-patch evidence

Each treatment trial initialized two atomic task commitments, then submitted
a production-engine `Override` patch:

- old `butter_1` slot: `active -> overridden`;
- new `alphabet_soup_1` slot: `active`, parented to the old slot;
- completed `cream_cheese_1` slot: remains active and physically satisfied;
- before/after canonical hashes differ and are recorded per state;
- `oracle_operation_selection=True`; `provider_called=False`.

This isolates the claim that **editing the persistent commitment changes
execution**.  It does not test whether an LLM can infer the correct patch.

## Failed cross-direction qualification

The same position-only controller was tested on Task 5 book-to-caddy back and
front targets.  Both initial attempts and both predicate-aware retries failed
(`0/4` target predicates), although grasp acquisition was `4/4` and lift was
about 0.20 m in every run.  The `descend_to_release` phase exhausted 40 steps
with 0.059–0.077 m residual error because the top-down gripper/caddy geometry
blocked entry.

Therefore the current controller is qualified for basket pick-place and
semantic object replacement, but **not** for narrow-compartment target
substitution.  Task 5 requires an orientation- and approach-conditioned
insertion skill; silently adding Task 5 to the main table would conflate CoPE
semantics with an unqualified low-level controller.

## Reproduction

CPU-only simulator invocation:

```bash
export HF_HOME=/home/lijingsu/vla/cache/huggingface
export TRANSFORMERS_CACHE=/home/lijingsu/vla/cache/transformers
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=""

scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  experiments/oracle_replacement_gate.py \
  --state-id 0 \
  --mode checkpoint_oracle_cope_patch \
  --output-csv research/oracle_skill_canary/replacement_gate/reproduction.csv
```

Repeat `--state-id` over `0..4` and `--mode` over
`original, reset_counterfactual, checkpoint_no_edit,
checkpoint_oracle_cope_patch`.

Primary tables:

- `research/oracle_skill_canary/task00_original_all.csv`
- `research/oracle_skill_canary/replacement_gate_all.csv`
- `research/oracle_skill_canary/target_geometry_all.csv`

## Next experiment

Freeze this controller and run more interruption types on basket-compatible
skills: cancellation, repeated replacement, and two sequential events.  In
parallel, qualify a learned explicit-goal skill policy as the non-oracle
controller stratum.  Do not return to ReKep as the sole main baseline unless
its clean gate is first raised above the predeclared threshold.
