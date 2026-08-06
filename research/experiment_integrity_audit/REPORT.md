# Oracle experiment integrity audit

Date: 2026-07-31

Scope: commits `3951609`, `7be9e74`, and `f493637` on
`codex/fsr-pc-v2-canary`, covering the oracle skill, repeated replacement,
and lift-time recovery canaries.

## Verdict

No evidence was found that the reported simulator successes were produced by
directly editing MuJoCo object state, inventing success rows without episode
files, or changing the reported success counts after aggregation. The
controller sends 7-D commands through `env.step`; the audited controller and
three runners contain no `qpos`, `qvel`, `set_state`, joint setter, or
`sim.forward()` mutation.

This is not the same as saying the old evidence is audit-grade. The old runs
are real privileged-oracle mechanism canaries, not learned-policy or
end-to-end CoPE evaluations. They also have two provenance gaps and one
concrete aggregation defect. Their claim level must therefore remain narrow.

## Checks performed

1. `git fsck --no-dangling` passed. Code, per-episode CSVs, text logs,
   aggregate tables, reports, and tests are present in the same commit chain.
2. A static mutation scan of the controller and the three experiment runners
   found no direct simulator-state write. All robot motion in the oracle
   controller goes through `env.step`.
3. Aggregate success identities were independently recomputed from simulator
   predicates. The repeated-replacement and lift-time headline counts agree
   with the per-episode predicate columns.
4. Aggregate rows were compared with their referenced episode CSVs. This
   exposed the revision-path defect below; no success/predicate discrepancy
   was found.
5. The five trials were verified to be LIBERO's five official initial
   layouts. They are not five random seeds and are not a powered sample.

## Defects and limitations found

### A1 — Repeated-replacement revision provenance mismatch

Severity: medium for provenance; no observed effect on physical success
counts.

The two-patch episode CSVs record `revision_path=1>2>2>3`, while the aggregate
table and report state `1>2>3`. The committed generator currently emits
`1>2>3`; the committed summarizer had silently replaced every two-patch raw
value with `1>2>3`.

This means the historical aggregate is not a byte-faithful concatenation of
the historical raw rows, and the historical two-patch raw files are not fully
reproducible from the committed generator. The summarizer is now changed to
reject a raw mismatch instead of normalizing it. The old raw files remain
unchanged as evidence. A clean rerun must go to a new path.

The clean state-0 two-patch rerun produced `revision_path=1>2>3`, accepted
both patches, retained cream cheese, placed tomato sauce, suppressed both
stale objects, and used exactly 359 environment steps. The historical state-0
raw row has the same physical predicates and 359 steps; only its revision-path
serialization differs. This narrows the defect to provenance/serialization
rather than the reported physical outcome, without erasing the mismatch.

### A2 — Physical truth was trusted from the runner

Severity: medium as a latent validation bypass; no contradictory predicate
was observed in the archived rows.

The old runners passed `physically_true_objects=(cream_cheese_1,)`
unconditionally after attempting the first skill. If that skill had failed,
the helper could have been given a false premise. Archived final predicates
show cream cheese in the basket in all reported rows, so this did not change
the published counts, but the evidence path was weaker than the report
implied.

All affected runners now derive the tuple from a fresh simulator predicate
query before applying a patch. False physical progress is passed as an empty
tuple and rejected by state validation.

### A3 — Old paired prefixes were inferred, not proven

Severity: medium for causal attribution.

The old arms have matching initial-state IDs and often identical event steps,
but they did not archive low-level action traces or simulator checkpoints.
Consequently, identical pre-event trajectories could only be inferred from
deterministic code. They were not cryptographically demonstrated.

The new timing experiment records a SHA-256 of every pre-event 7-D action
prefix and a SHA-256 of the full MuJoCo state plus controls. A pair is rejected
unless both hashes, event step, EEF pose, and held-object pose match. It also
requires the semantic patch to emit no action and leave the simulator-state
hash unchanged.

### A4 — Oracle and custom-goal boundary

Severity: high if results are mislabeled; acceptable for a mechanism canary.

Object identity, event time, replacement operation, object/region geometry,
and recovery choice are oracle. `provider_called=False`; no learned policy or
event interpreter is evaluated. Updated-goal success is a conjunction of
fresh simulator predicates because the original LIBERO BDDL task still names
butter. It is not official LIBERO task success for the updated instruction.

### A5 — Safety evidence is narrow

The lift-time experiment verifies grasp retention, release, return-position
error, object predicates, and a 600-step budget. It does not measure force,
contact impulse, collision severity, or human safety. “Safe return” denotes
the recovery operator's intended function, not a comprehensive safety claim.

## Evidence classification

| Evidence | Physical simulator execution | Raw outcome consistency | Paired-prefix proof | Permitted claim |
|---|---:|---:|---:|---|
| Oracle skill/replacement | yes | yes | no | execution-substrate mechanism canary |
| Repeated replacement | yes | success rows yes; revision provenance defect | no | persistent-state mechanism canary, downgraded |
| Lift-time recovery | yes | yes | no | executable-repair mechanism canary |
| New timing sensitivity | yes | validated by strict summarizer | yes | audit-strength oracle mechanism canary only |

## New timing experiment result

The replacement-timing rerun contains 30 real simulator episodes: five
official layouts, three event timings, and two independently reset arms. All
15 pairs match on low-level action-prefix SHA-256, MuJoCo-state SHA-256, event
step, EEF pose, and held-object pose. All patches emit zero actions and leave
the MuJoCo-state hash unchanged.

- post-lift: stale 0/5 versus exact return-and-switch 5/5 within 600 steps;
- mid-transfer: stale 0/5 versus exact return-and-switch 5/5;
- pre-release: stale 0/5 versus exact return-and-switch 3/5 within the budget.

All five pre-release exact-return arms physically reached the updated goal,
but state 3 required 607 steps and state 4 required 601. State 1 finished at
599. Thus the late failures are a recovery-cost boundary, not semantic-patch
rejection. The failed horizon gates are retained in the aggregate and report.

The follow-up local-staging repair also preserves the exact pre-event hashes.
Its first, more aggressive 20 cm staging point failed honestly: the obsolete
object was released outside the basket but missed the position tolerance by
93 mm, so the runner refused to execute the replacement skill. That raw pilot
is retained. Moving the staging target to a point 25% short of the object's
known stable original pose then passed 5/5 layouts in 544–569 steps, versus
3/5 within the horizon for exact return. It saved 30–38 steps and had a
maximum staging error of 6.32 mm. This remains an oracle repair-policy canary,
not a learned or comprehensive safety result.

## Final verification

- Full repository test suite: `294 passed in 45.88s`.
- The revised repeated-replacement summarizer exits nonzero on the archived
  `1>2>2>3` row and explicitly refuses to normalize it.
- No audited experiment or test process remained after collection.
- Raw and aggregate CSV hash manifests are stored with both new experiments.

## What this audit does not prove

Git history and consistent raw rows cannot prove the absence of all manual
intervention before files were committed. The strongest honest conclusion is
that no fabrication mechanism was found, the physical outcomes are consistent
with executable simulator code, one real provenance defect was detected, and
the old evidence lacks enough trajectory material for full forensic replay.
The new experiment is designed to close the specific causal-pairing and
physical-truth gaps, while retaining the explicit oracle limitation.
