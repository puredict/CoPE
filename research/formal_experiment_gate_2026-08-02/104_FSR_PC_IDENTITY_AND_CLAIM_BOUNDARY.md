# FSR-PC identity and claim boundary

Date: 2026-08-04 (Asia/Shanghai)

## Finding

**FSR-PC is a project-internal experimental arm, not a verified name of a
published robot-recovery method.**  The repository operationalizes it as a
metadata-free canonical full semantic-state rewrite followed by the shared
validator/compiler path.  The repository does not provide a paper citation or
a frozen expansion of the letters `FSR-PC`.

An exact-name public search for `"FSR-PC" robotics` and `"FSR-PC" robot`
returned unrelated uses (force-sensitive resistors, Field and Service Robotics
program committees, electronics and networking).  No relevant primary robot
recovery paper was found.  This is a bounded search result, not proof that no
such string exists anywhere.

## Repository evidence

- `cope/prompts/fsr_pc_full_state_v2.txt` calls it a canonical full-state-v2
  rewrite.
- `cope/sequential_prompting.py` requires the complete post-event semantic
  state and forbids transaction metadata.
- `fresh_state_recovery_2026-08-01/05_FSR_PC_READINESS_AUDIT.md` defines the
  fairness target as common input, neutral validation and a shared compiler.
- `formal_experiment_gate_2026-08-02/88_REVIEWER_SIMULATION_AFTER_NOVELTY_AUDIT.md`
  explicitly says FSR-PC and full-replan schemas are operationalizations, not
  automatically literature baselines.

## Required paper terminology

Use one of the following descriptions:

> internal canonical full-state regeneration baseline (FSR-PC arm)

or, preferably after a non-outcome-affecting naming amendment:

> matched full-state regeneration baseline

Do not write “the FSR-PC method”, imply that a cited paper proposed this exact
schema, or use its failure as evidence against all full-state recovery or
replanning systems.

## What the comparison can test

At matched input, model, seed, call budget, neutral semantic validation and
shared downstream execution, the comparison can test the effect of requiring a
model to regenerate the complete state rather than emit a local update under
this frozen representation contract.  It cannot isolate intrinsic model
intelligence, prove that full-state recovery is generally inferior, or stand
in for strong published systems that use different memory, graphs, planners,
decoders or verification.

The primary causal control remains the equally expressive neutral sparse
transaction.  FSR-PC is secondary and cannot rescue a CoPE-neutral tie.

