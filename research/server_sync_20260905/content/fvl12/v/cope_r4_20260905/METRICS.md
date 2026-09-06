# Metrics

All computed by one function, [`cope/benchmark/metrics.py`](../cope/benchmark/metrics.py)
`::evaluate_episode`, identically for every arm, from the shared store, the
shared audit trace and the shared executor log.

`None` means **not applicable to this episode**, never "failed".

## 1. Final behaviour

| metric | definition |
|---|---|
| `revised_task_success` | every object in the **revised** target basket, and no cancelled object placed |
| `collision` | any collision reported by the executor |
| `safe_fallback` | the policy's patch/regeneration was rejected by validation and the state was left untouched |
| `invalid_action_count` | actions the executor physically could not perform (missing target, no target) |
| `completion_steps` | total executor steps |

## 2. Progress and continuity

| metric | definition |
|---|---|
| `completed_progress_preserved` | no goal completed *before* the first adaptation is executed again *after* it |
| `completed_goals_repeated` | count of such repetitions |
| `cancelled_goal_violations` | placements of an object whose goal was cancelled |
| `stale_goal_executions` | placements against a target that is no longer the expected one |
| `remaining_goal_correct` | the state left behind asks for exactly the right remaining work — right targets, nothing cancelled |
| `recovery_after_repeat` | success under I3 (two consecutive edits to the same goal) |

## 3. State representation

| metric | definition |
|---|---|
| `identity_preserved` | every slot id present before the first adaptation still exists afterwards |
| `lifecycle_transitions_legal` | every pre/post validation passed |
| `restore_preceded_by_revalidation` | every `Restore` was preceded by a `Revalidate` on the same slot (`None` if the episode restores nothing) |
| `invalid_restore_count` | restores without a preceding revalidation |
| `lineage_correct` | override edges symmetric and acyclic |
| `history_monotonic` | per-slot `seq` strictly increasing, no duplicates |

## 4. Editing vs regeneration

| metric | definition |
|---|---|
| `slots_edited` | total slots touched across the episode |
| `slots_regenerated` | total slots re-emitted across the episode (0 for CoPE by construction) |
| `slots_touched_per_event` | mean slots touched per interruption |
| `ops_per_event` | mean typed operations per interruption |
| `normalized_edit_distance` | mean over interruptions of `touched / state size` — in `[0, 1]`, and **1.0 for full regeneration by definition** |
| `state_churn` | fraction of interruptions that changed the state fingerprint |
| `planner_calls` | adaptation calls made |
| `adaptation_latency_s` | wall-clock seconds spent inside `policy.adapt` |
| `token_usage` | `None` — neither arm uses a language model, so no token claim is made |

Normalisation is **per interruption**, not per episode, so the figure stays in
`[0, 1]` and is comparable across conditions with different numbers of
interruptions.

## 5. Audit

| metric | definition |
|---|---|
| `audit_answerable` | per query: `True` answered, `False` asked-and-unanswerable, `None` not posed by this condition |
| `audit_coverage` | fraction of the **applicable** queries answered (`None` if the condition poses none) |

Applicability per condition is fixed in
`cope/benchmark/basket_task.py::AUDIT_APPLICABILITY` and is the same for every
arm:

| condition | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| nominal | – | – | – | – | – |
| I1 | ✓ | ✓ | – | – | ✓ |
| I2 | – | ✓ | ✓ | ✓ | – |
| I3 | – | ✓ | – | – | ✓ |
| I4 | – | ✓ | ✓ | ✓ | – |

Every query has both a patch-evidence path and a regeneration-evidence path, so
the metric is not circular. See [`COPE_METHOD.md §6`](COPE_METHOD.md).

## 6. CPU pilot results (5 paired seeds × 4 conditions)

Binary, exact McNemar:

| metric | CoPE | FSR-PC | p |
|---|---|---|---|
| `revised_task_success` | 20/20 | 20/20 | 1.000 |
| `completed_progress_preserved` | 20/20 | 20/20 | 1.000 |
| `remaining_goal_correct` | 20/20 | 20/20 | 1.000 |
| `identity_preserved` | 20/20 | **0/20** | <0.001 |
| `lifecycle_transitions_legal` | 20/20 | 20/20 | 1.000 |
| `lineage_correct` | 20/20 | 20/20 | 1.000 |
| `history_monotonic` | 20/20 | 20/20 | 1.000 |

Continuous, paired bootstrap 95% CI on `CoPE − FSR-PC`:

| metric | CoPE | FSR-PC | 95% CI | excludes 0 |
|---|---|---|---|---|
| `normalized_edit_distance` | 0.507 | 1.000 | [−0.541, −0.442] | yes |
| `slots_touched_per_event` | 3.000 | 5.125 | [−2.500, −1.725] | yes |
| `audit_coverage` | 1.000 | 0.458 | [+0.483, +0.600] | yes |
| `completion_steps` | 165.0 | 165.0 | [0.000, 0.000] | no |
| `invalid_action_count` | 0.000 | 0.000 | [0.000, 0.000] | no |

**Honest reading.** The arms are tied on every behavioural outcome. The
differences are in state representation, edit locality and audit answerability
— which is what the method claims and what the metrics were designed to expose.
`normalized_edit_distance = 1.000` for FSR-PC is true **by definition of full
regeneration**, so it is a description of the two designs, not an experimental
finding; the informative numbers are the audit coverage gap and the ablation
that separates identity from locality.

These are CPU numbers from a mock executor. They validate the protocol,
semantics and fairness controls. They are not a robotics result.

---

# r2 additions

## Failure layers (replaces the single conflated success flag)

Per episode: `event_schedule_valid`, `all_required_events_delivered`,
`adaptation_input_valid`, `state_update_valid`, `patch_or_regeneration_valid`,
`continuation_captured`, `repair_goal_compiled`, `candidate_generation_complete`,
`rollout_verification_complete`, `graph_splice_complete`,
`restore_event_delivered`, `revalidation_performed`, `restore_contract_valid`,
`stage_resumed`, `controller_success`, `grasp_success`, `placement_success`,
`revised_task_success`, `infrastructure_failure`, `controller_failure`,
`adaptation_failure`, `task_failure_reason`.

Deterministic hierarchy: **infrastructure → adaptation → controller → task**.

> A correct CoPE or FSR-PC state update followed by a failed grasp is a
> **controller failure**, never an adaptation failure. This is the v2
> mislabelling that made 8 episodes look like method failures.

## Interruption-level records (`interruptions.jsonl`)

`episode_id`, `method`, `condition`, `seed`, `event_index`, `event_type`,
`scheduled_step`, `delivered_step`, `task_state_before`, `task_state_after`,
`physical_world_change`, `affected_goal_ids`, `old_target`, `new_target`,
`patch_operations`, `regenerated_state_hash`, `continuation_id`,
`repair_invocation_id`, `restoration_required`, `revalidation_result`,
`restoration_result`.

These distinguish *event never delivered* from *delivered but adaptation failed*
from *adaptation correct but the controller failed*.

## Auditability — eight questions, three evidence paths

What changed; why; which event caused it; which old state was replaced; what
condition allowed restoration; whether revalidation occurred; why a candidate
was rejected; why the final candidate was selected. Evidence may come from typed
patch operations, snapshot diffs, or per-slot provenance.

**r2 CPU finding:** stable IDs do not close the audit gap; explicit provenance
almost entirely does (see `CHANGELOG.md`). Report the audit advantage as
attributable to *recording provenance*, except under I5 where a residual gap
remains.
