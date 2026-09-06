# Fair-comparison protocol — CoPE vs FSR-PC

Every control below is implemented in **one** place —
[`cope/benchmark/episode.py`](../cope/benchmark/episode.py) — so it cannot drift
between arms, and every one is asserted by a test in
[`tests/test_cope_fairness.py`](../tests/test_cope_fairness.py) rather than
promised in prose.

## F1 — same task, same seed, same layout, same interruption timing

`BasketTaskSpec.key()` deliberately excludes the method, so pairing is by
`(task, condition, seed)`. Conditions are deterministic in `(condition, seed)`.
The initial state — including the scripted execution order — is built before any
policy object exists.

- `test_pairing_key_excludes_the_method`
- `test_every_arm_starts_from_the_identical_initial_state`
- `test_interruption_timing_does_not_depend_on_the_method`

## F2 — same information

At each interruption both arms receive one `AdaptationInput` built from
**method-independent facts only** (canonical goal ids, completed objects, world
state, full task and event history, safety constraints, perception, budget).
The packet is serialized and fingerprinted.

**Result: the fingerprints are byte-identical at every event, for all four
conditions × three seeds.**

- `test_both_primary_arms_receive_byte_identical_adaptation_inputs`
- `test_fsrpc_is_not_made_forgetful`

### The one legitimate divergence, stated explicitly

The `no_adaptation` control arm can see a *different second packet* in I2/I4.
That is not an information asymmetry: it burned an action on an unavailable
target, so its task history genuinely differs. The **first** packet is identical
for all three arms, which is the information test
(`test_the_control_arm_may_diverge_only_through_its_own_behaviour`).

For CoPE vs FSR-PC — the comparison the paper makes — the packets are identical
at *every* event, not only the first.

## F3 — same executor and the same interface

Both arms return an `ExecutorRequest` produced by the shared
`StateStore.compile_active()`. The executor object, its parameters and its
random stream are shared, and the stream is keyed on the physical action so both
arms get common random numbers.

- `test_both_arms_use_the_same_executor_interface`
- `test_the_executor_cannot_tell_which_policy_produced_the_request` — the
  compiled request contains no method marker anywhere in its serialization.

## F4 — same budget, horizon, grader and metric code

`compute_budget` (`max_planner_calls=4`, `max_seconds=30`) and
`horizon_steps=900` are identical. The grader depends only on the condition.
Every metric is computed by one function, `evaluate_episode`, from the shared
store, the shared trace and the shared executor log — never from
policy-private structures.

## F5 — no cross-contamination

Neither arm observes the other's output. Episodes are independent; the store,
trace and executor are constructed fresh per episode.

## Statistical protocol

- **Pairing** by `pairing_key` (method excluded).
- **Binary outcomes**: exact McNemar on the discordant pairs; Wilson 95%
  intervals for each arm's rate.
- **Continuous outcomes**: paired bootstrap (10 000 resamples, seed 0) for
  `mean(CoPE) − mean(FSR-PC)`.
- **Multiplicity**: Holm–Bonferroni across the binary family.
- Reused unchanged from the frozen CPU work:
  [`rekep_repair/benchmark/statistics.py`](../rekep_repair/benchmark/statistics.py).

Reporting rules carried over from the earlier phase and still in force:

- Do not tune thresholds to manufacture significance.
- Report null results as null. A tie is a tie.
- Do not classify simulator non-determinism as a method failure without
  evidence.

## Ablations (Stage C) — mechanism, not rhetoric

| ablation | question it answers |
|---|---|
| `FSR-PC(preserve_ids=True)` | is the CoPE advantage just id bookkeeping? |

Answer from the pilot: **no.** Preserving ids recovers the identity metric and
changes neither edit locality (NED stays 1.000) nor audit coverage (stays
0.458). See [`FSRPC_BASELINE_SPEC.md §5`](FSRPC_BASELINE_SPEC.md).

## What a reviewer should attack, and where to look

1. *"The baseline is a straw man."* → §F2, `FSRPC_BASELINE_SPEC.md §3`, and the
   byte-identity test.
2. *"The audit metric is circular."* → `audit_trace.py` gives every query a
   regeneration evidence path; FSR-PC answers Q1 and Q2.
3. *"The task is too easy / the control wins for free."* →
   `test_no_condition_is_won_for_free_by_the_control_arm`.
4. *"The gate is vacuous."* → `test_the_gate_is_not_vacuous`.
5. *"CoPE was given a better executor / seed / grader."* → F1, F3, F4, all
   asserted.

---

# r2 additions

## F7 — the event schedule is method-independent

The scheduler is constructed from `(condition, seed)` before any policy object
exists; `spec.method` is never passed to it. Each episode records a
`schedule_fingerprint`, and `test_paired_arms_get_the_identical_schedule`
asserts that all five arms produce the same fingerprint and the same scheduled
steps. Method identity therefore cannot affect physical event scheduling.

## F8 — the compiled repair goal is representation-neutral

CoPE expresses a withdrawn detour as `Expire(cover) + Restore(original)`, while
FSR-PC re-emits one slot whose target reverts. These landed on different
branches of the goal compiler and produced **different repair goals for the same
semantic change** — caught by `test_paired_arms_compile_identical_repair_goals[I5]`.
The compiler now compares the canonical *live* target directly, so both
representations compile identically. The `target_relocated` predicate is derived
the same way.

## F9 — the audit score is not defined by CoPE operator names

Every audit query has three evidence paths: typed patch operations, diffing
consecutive regenerated snapshots, and **per-slot provenance**. Any method may
emit provenance; `FSR-PC_provenance` does, and its coverage rises accordingly.
`test_audit_scoring_is_not_defined_by_cope_operator_names` asserts the metric
responds to it.

## FSR-PC variants are not weakened

All variants receive the same complete `AdaptationInput`, the same compute
budget, and the same downstream repair stack. None may apply a CoPE patch
(`assert_no_patch_application`, asserted by test). None hides history or
progress (`test_no_variant_is_weakened_by_hiding_history_or_progress`).
