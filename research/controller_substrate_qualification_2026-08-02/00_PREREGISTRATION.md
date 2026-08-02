# Explicit-goal controller substrate qualification preregistration

Date frozen: 2026-08-02 (Asia/Shanghai)

Parent implementation commit: `9953aaf52cded2fbe43cb68e346794f85b29ddd9`

Branch: `codex/oracle-substrate-qualification`

## Decision question

Can the existing basket-compatible `LiberoOracleSkillController` serve as a
frozen execution substrate for CoPE--FSR-PC replacement experiments when the
controller exposes object/region arguments and supports continuation from a
held-object checkpoint?

This is a confirmatory qualification on already-consumed development states,
not a blinded evaluation. Prior 5/5 basket canaries are known before this
preregistration. The controller is privileged and position/geometry based. It
must never be called a learned manipulation system.

## Frozen scope

- LIBERO-10 task 1 only; basket pick-and-place.
- State indices 0--4 only. These are already-consumed development layouts.
- No state 25--49 may be indexed, reset, hashed individually, rendered,
  summarized, compared, or used for controller adjustment.
- The upstream init-state container is monolithic. Its whole-file load is an
  unavoidable runtime dependency; only indices 0--4 may be selected. Every
  episode records this distinction explicitly.
- CPU simulator execution with `CUDA_VISIBLE_DEVICES=""`; no GPU, training,
  model download, or learned policy.
- Frozen controller defaults except `max_move_steps=60`, which was fixed on
  already-consumed state 5 before this qualification and is applied uniformly.
- No parameter may be selected using the assigned results.

## Frozen qualification matrix

`02_QUALIFICATION_MANIFEST.csv` assigns five states to these arms:

1. original task clean from reset;
2. updated goal clean from reset;
3. checkpoint plus no-edit stale control;
4. checkpoint plus oracle full-state updated goal;
5. checkpoint plus oracle CoPE-patch materialized updated goal;
6. no-event plain and semantic-scaffold parity;
7. post-lift, mid-transfer, and pre-release stale/local-stage pairs;
8. repeated replacement second-event-no-edit/double-patch pair.

The checkpoint is the deterministic state reached after putting
`cream_cheese_1` in `basket_1_contain_region`. In-motion checkpoints additionally
hold `alphabet_soup_1` at the frozen phase boundary.

## Pairing and provenance gates

Every episode records an initial or event checkpoint action-prefix SHA-256 and
MuJoCo-state SHA-256. Arms are grouped only when their comparison checkpoint is
semantically and physically matched. A comparison group passes provenance only
if 100% of its members have identical action-prefix, simulator-state, step,
EEF-pose, and held-object-pose fields applicable to that group. Semantic edits
must emit zero simulator actions and preserve the simulator-state hash.

Reset-goal arms share the post-warmup initial checkpoint. Milestone arms share
the completed-cream checkpoint. Timing pairs share the held-object event
checkpoint. Repeated-event pairs share the checkpoint before the second event.
Method-independent failures before the comparison checkpoint remain in the
assigned denominator and are reported separately; they are never silently
rerun or excluded.

## Frozen pass gates

All denominators are the five assigned states.

- original reset success: at least 4/5;
- updated-goal reset success: at least 4/5;
- checkpoint oracle-full updated-goal success: at least 4/5;
- checkpoint oracle-patch updated-goal success: at least 4/5;
- checkpoint no-edit: stale original goal executed in at least 4/5 and updated
  goal succeeds in at most 1/5;
- valid completed progress retained in at least 4/5 for each checkpoint
  treatment arm;
- stale pending action suppressed in at least 4/5 for both oracle-full and
  oracle-patch arms;
- no-event parity: both arms succeed in at least 4/5, paired terminal predicates
  are identical in 5/5, and their success-rate difference is 0 percentage points;
- local-stage recovery reaches the updated goal and suppresses the stale held
  object in at least 4/5 at each of post-lift, mid-transfer, and pre-release;
- the matched stale arm executes the obsolete held object in at least 4/5 and
  reaches the updated goal in at most 1/5 at each timing;
- repeated double patch reaches the final updated goal and suppresses both stale
  objects in at least 4/5; ignoring event two executes the first replacement in
  at least 4/5 and reaches the final goal in at most 1/5;
- paired prefix/provenance integrity: 100% across every assigned comparison;
- semantic mutation integrity: 100%; reserved-state indexing: 0; GPU/provider/
  learned-policy calls: 0.

A substrate-level PASS requires every gate above. Any failure yields FAIL for
the proposed basket qualification, with no threshold change or held-out tuning.

## Interpretation rule

A PASS qualifies the controller only for the `oracle/mechanism` stratum on
