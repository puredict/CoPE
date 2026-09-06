# Task semantics and evidence status: LIBERO-10 tasks 0, 1, 4, 8

This document combines actual source bytes, reset checks and isolated simulator-effect witnesses. It creates no catalog entry, occurrence allocation, safe-event certificate or experiment result. Further experiments were not run after the authorized witness sweep.

The old all-ten-families-per-task discussion in FEASIBILITY_EXECUTION_PLAN.md is historical and superseded by [FAMILY_SCOPE_AUDIT.md](FAMILY_SCOPE_AUDIT.md) and the current corrected task_catalog.py/scheduler.py. Current code validates resolved task-specific support, chooses supported grounding/retirement alternatives, and retains unknown/duplicate/unresolved support failures. The unchanged eight-event template still requires both temporary pairs, preference, reissue and one supported grounding/retirement variant; global library coverage and minimum-eight-task admission remain separate. None of these changes certifies the four tasks.

## Evidence boundaries

- [STATIC_TASK_EVIDENCE.txt](STATIC_TASK_EVIDENCE.txt) retains exact remote BDDL text/file hashes, task-progress declarations and original family candidates; [STATE_HASHES.csv](STATE_HASHES.csv) contains20 CPU-verified state receipts.
- [Reset receipt](reset_feasibility_20260906T171329Z_618e9be2/RECEIPT.txt) covers four tasks ×five states. Declared joints exist and all20 reset EEFs lie outside the old no-go boxes. Predicate-count labels are declarations, not verified independence.
- [Effect counts](event_effect_20260906T171946Z_1f2fc64b/EFFECT_COUNTS.csv), [raw effects](event_effect_20260906T171946Z_1f2fc64b/EVENT_RESULTS.txt), [exact restorations](event_effect_20260906T171946Z_1f2fc64b/CASE_RESTORATIONS.txt) and [independent accounting](event_effect_20260906T171946Z_1f2fc64b/COPY_VERIFICATION.txt) establish135 returned mechanical witnesses,135 passing checks,95 exact isolated restorations, zero failures/skips and zero environment-control attempts. No provider/VLA/GPU calls occurred.
- The effect records contain simulator object-state observations and privileged before/after qpos/qvel. They are harness audit evidence, not public perception inputs. Cameras were disabled. Fresh forced-observation equality is not a rendered-RGB perception certificate.
- Calibration outcomes, actual native-VLA gate and current catalog gap totals are owned by the separate readiness report. No success rate or qualification is inferred here.

## Original clauses, semantic families and milestone candidates

The following nine clauses exactly match actual BDDL goals. Family keys follow the existing catalog naming convention; they are semantic families, not allocated occurrences. Existing progress names are source declarations. All milestone interpretations remain SOURCE_DERIVED_UNQUALIFIED until independent observation, preservation and task relevance are evidenced.


| Task | Original predicate(arguments) | Candidate family | Existing progress name |
|---|---|---|---|
| 0 | in(alphabet_soup_1, basket_1_contain_region) | goal:in:alphabet_soup_1:basket_1_contain_region | alphabet_soup_in_basket |
| 0 | in(tomato_sauce_1, basket_1_contain_region) | goal:in:tomato_sauce_1:basket_1_contain_region | tomato_sauce_in_basket |
| 1 | in(cream_cheese_1, basket_1_contain_region) | goal:in:cream_cheese_1:basket_1_contain_region | cream_cheese_in_basket |
| 1 | in(butter_1, basket_1_contain_region) | goal:in:butter_1:basket_1_contain_region | butter_in_basket |
| 4 | on(porcelain_mug_1, plate_1) | goal:on:porcelain_mug_1:plate_1 | white_mug_on_left_plate |
| 4 | on(white_yellow_mug_1, plate_2) | goal:on:white_yellow_mug_1:plate_2 | yellow_white_mug_on_right_plate |
| 8 | on(moka_pot_1, flat_stove_1_cook_region) | goal:on:moka_pot_1:flat_stove_1_cook_region | right_moka_pot_on_stove |
| 8 | on(moka_pot_2, flat_stove_1_cook_region) | goal:on:moka_pot_2:flat_stove_1_cook_region | left_moka_pot_on_stove |
| 8 | turnon(flat_stove_1) | goal:turnon:flat_stove_1 | stove_remains_on |

Task0 and task1 each have two different placement predicates sharing basket_1_contain_region. Task4 has two placements with distinct specified plates. These provide identifiable candidate subgoals; a conjunction alone does not show independent achievability or that one remains valid during interruption of the other.

Task8 contains two moka-pot placement clauses plus Turnon(flat_stove_1). Turnon also occurs in the BDDL initial state. Existing task_progress calls it stove_remains_on. It is an operational commitment candidate, not evidence of a newly achieved third placement. This document does not silently reclassify its current catalog role or use it to manufacture a second independent milestone.

Source identity aliases are exact simulator entity/region names, not guesses from language:


| Task | Task-target identity aliases | Receptacle / region bindings |
|---|---|---|
| 0 | alphabet_soup_1→alphabet_soup_1; tomato_sauce_1→tomato_sauce_1 | basket_1_contain_region |
| 1 | butter_1→butter_1; cream_cheese_1→cream_cheese_1 | basket_1_contain_region |
| 4 | plate_1→plate_1; plate_2→plate_2; porcelain_mug_1→porcelain_mug_1; white_yellow_mug_1→white_yellow_mug_1 | plate_1; plate_2 |
| 8 | moka_pot_1→moka_pot_1; moka_pot_2→moka_pot_2 | flat_stove_1; flat_stove_1_cook_region |

The complete source audit also retains distractor object aliases, fixture types, initialization regions and all available initial-state-file hashes. Initialization regions are placement-randomization definitions; they are not automatically admissible replacement goals or certified safe interruption poses.

## Task-specific semantic assessment

| Area | Task0 | Task1 | Task4 | Task8 |
|---|---|---|---|---|
| Achievement candidates | Soup-in-basket; sauce-in-basket | Cream-cheese-in-basket; butter-in-basket | White mug on plate1; yellow/white mug on plate2 | Two pots on stove |
| Preservable milestone candidate | One placement while the other remains pending | One placement while the other remains pending | One specified mug/plate relation while the other remains pending | One pot/stove relation while the other remains pending |
| Maintenance candidate | Preserve completed sibling placement, if independently verified | Same | Preserve correct sibling mug/plate assignment | Preserve completed pot placement and existing stove-on condition |
| Grounding primitive evidence | Actual target and basket motion witnessed | Actual target and basket motion witnessed | Actual one-target and one-plate motion witnessed | Actual one-pot motion witnessed; stove motion unsupported |
| Persistent preference candidate | Existing handle-gently contract has two manipulation stages | Same | Two mug manipulations | Two pot manipulations |
| Replacement / valid alternative | Unresolved | Unresolved | Unresolved; swapping plate identities is not authorized by BDDL | Unresolved; stove initialization region is not a goal alternative |
| Cancellation / reissue | Known family can parameterize software protocol; live semantics unqualified | Same | Same, preserving exact plate assignment | Same; original stove-on requirement must not disappear implicitly |
| Independent preservation / trigger certificate | Missing | Missing | Missing | Missing |

No hard-safety constraint set or semantic preference threshold is certified merely from these candidate statements. The old no-go and gentle values are existing experimental candidates. Cross-skill relevance, binding to accepted commitments and scoring meaning remain to be established. A successful reset or immediate injection does not demonstrate a completed placement remains stable after settling or during another skill.

## Cancellation and reissue protocol templates: software only

These are representation-neutral semantic templates tied to existing source families, not actual user messages, model outputs, initialized ledger records or tested live interventions. They allocate no IDs. The public event should carry a grounded utterance and its timestamp/provenance/evidence references; expected operations and hidden canonical effects must remain outside ordinary model inputs.

For a source family F with current occurrence F@n, a cancellation template is: “Cancel the current request to satisfy <the exact predicate and arguments of F>; keep other requirements.” The intended applicability change is ACTIVE→EXPIRED for that occurrence, preserving its historical bytes and keeping unmentioned goals/constraints protected. The typed carrier's existing EXPIRE operation is one serialization; generic and full-state carriers express the same intended semantics through their own contracts. There is no simulator teleport implied by cancellation.

A later reissue template is: “Request <the same exact source predicate and arguments> again.” The old expired/overridden occurrence remains retired. A trusted allocator issues a fresh F@m, where m exceeds the family maximum in accepted history; F@n must never be reactivated as a reissue. The new record needs explicit grounded predicate/arguments, role, authority, hardness, priority, provenance and evidence. Those fields are not filled here from guesses. Source-family lineage may be represented by valid same_family/derived_from relations when explicitly required by the event contract.

These templates can refer to either placement family for each task. In task4 they must retain the exact porcelain_mug_1→plate_1 or white_yellow_mug_1→plate_2 binding. In task8 a pot reissue does not cancel Turnon(flat_stove_1) or other unmentioned commitments.

Existing software support:

- occurrence.py requires family@positive-integer IDs, excludes duplicate active occurrences of an exclusive family, allocates monotonically and permits reissue only from trusted retired history.
- state_engine.py rejects mutation of expired/overridden slots, requires protected unmentioned occurrences and a matching protected-projection hash, and allocates new requested slots in the kernel.
- patch_contract.py represents cancellation through EXPIRE and insertion through INSERT. The runtime kernel resolves allocation request IDs. occurrence.reissue is a trusted identity helper, not a model-controlled ID choice.
- RESTORE is distinct: it retains the same suspended occurrence only after fresh, successful, occurrence/event/revision/guard-bound validation. A clear/available event alone is not proof of restoration.
- SealedDynamicEvaluator rejects a canonical reissue that reuses a retired ID and records actions targeting inactive/unknown/non-goal occurrences.

These software rules do not establish that a real user utterance is interpreted correctly, that an event targets a currently active task occurrence, or that the resulting task is feasible.

Replacement requires a different explicitly accepted goal with evidence of validity, a fresh occurrence and an overrides relation retiring the prior occurrence. No qualified replacement goal was found for these tasks. Existing distractors, free space, BDDL initialization regions or another task's receptacle are not evidence of valid alternatives. Cancellation may be a task-supported retirement variant without inventing replacement support, once its real semantic/event feasibility is certified.

## Actual candidate parameters exercised

Each row below represents one existing manifest payload family, reused across the five audited initial states as an isolated mechanical test. It does not cover every target, every sign/direction, arbitrary coordinates or online interruption boundaries.


| Task | Target move (joint; dx,dy) | Receptacle move | Availability pair (joint; unavailable→release) |
|---|---|---|---|
| 0 | alphabet_soup_1_joint0; (-0.08,-0.06) | basket_1_joint0; (-0.06,-0.05) | tomato_sauce_1_joint0; [0.43, 0.41, 0.48]→[-0.24, 0.28, 0.48] |
| 1 | cream_cheese_1_joint0; (-0.08,-0.06) | basket_1_joint0; (0.06,-0.05) | butter_1_joint0; [0.43, 0.41, 0.44]→[-0.24, 0.28, 0.44] |
| 4 | porcelain_mug_1_joint0; (0.08,0.06) | plate_1_joint0; (0.06,-0.05) | porcelain_mug_1_joint0; [0.43, 0.41, 0.48]→[-0.24, 0.28, 0.48] |
| 8 | moka_pot_1_joint0; (-0.08,-0.06) | Unsupported stove free-joint motion | moka_pot_1_joint0; [0.43, 0.41, 0.97]→[-0.24, 0.28, 0.97] |

The no-go pair used world AABB minimum[-0.08,0.10,0.43], maximum[0.08,0.20,0.90] for tasks0/1/4; task8 used z bounds[0.92,1.30] with the same XY. The exact source payload declares physical_collision=false and visual_marker=false. Clearing removed the same active zone identity.

The existing gentle-preference payload used translation_ceiling0.035, EEF-speed ceiling0.22 and contact-impulse-proxy ceiling0.12. Actual ledger activation was witnessed; no policy compliance, physical unit calibration or cross-skill effectiveness was tested.

The exact availability-box endpoints are retained in raw records. All used XY bounds[-0.35,0.35]×[-0.36,0.36], with target-dependent z intervals. “Inside the box” is the implemented predicate, not a reachability or safe-grasp proof. Release placed the target at the explicit candidate coordinate; it did not restore a pre-event pose.

Tasks0/1/4 each produced35 application witnesses (seven primitive families ×five states). Task8 produced30 (six ×five), with stove relocation explicitly UNSUPPORTED_THIS_PRIMITIVE, not a failure assigned to unrelated families. Total135. Source triggers and legacy formal-seed labels were retained as provenance, but execution was at isolated probe policy_step0 with no scheduler. Thus no legal v2 trigger, minimum spacing, continuous trajectory or safety admission was tested. Each case's snapshot restoration was audit cleanup, never production recovery behavior.

The executed driver's generic labels would count skipped rows as applications if failures occurred. Independent audit confirms every one of the actual135 rows contains a returned application, with zero skips; scheduled=attempted=returned=passed for this run. Future reuse must fix separate counters, without overwriting this evidence.

## Semantic-trigger eligibility

Current SemanticTrigger requires an explicit semantic predicate and physical feasibility guard; fixed-step/fallback-only names are rejected. Task catalog windows must lie within0..260 with at least10 steps between events. evaluate_trigger separately checks prior failure, missed window, earliest step, spacing, named semantic fact, named feasibility fact and ungrasped-object status unless explicit forced displacement applies.

Source progress names can suggest candidate predicates such as “first named placement satisfied while the second is pending.” They are not registered current v2 trigger definitions. Each task still needs a verified task-local monitor binding, real qualifying boundary, held-object state, feasibility-guard evidence and state coverage. The receipt's arbitrary reset boundary and immediate paired operations must not populate these fields.

Current task-specific support correction means a task need not support an unused alternative grounding or retirement family. Empty/unresolved support still cannot erase gaps. The eight-event template's remaining requirements and experiment-wide union coverage must be checked separately. No family support set is certified in this document.

## Dynamic predicate and production binding gaps

The original in/on/turnon predicates have a real sealed source reader: LiberoStateView.libero_predicate delegates to env._eval_predicate. This is appropriate for harness scoring. It is privileged simulator truth and cannot become a reasoner/planner/policy observation.

A production runtime must map each active canonical occurrence's exact predicate+arguments to a supported Boolean reader, update only the hidden canonical timeline from actual events, bind completed-milestone certificates to authentic verifier records, and keep that timeline out of all method inputs. The original fixed _check_success conjunction is insufficient after cancellation/replacement because active task requirements may have changed.

SealedDynamicEvaluator requires literal bool and fails closed on unavailable predicates. It scores active goals, hard constraints, wrong-occurrence execution, completed-step regression, required-event reachability and timeout/manual intervention. The current production RuntimeEnvironment.sealed_predicate/public_context/inject and complete EpisodeInputs assembly remain unbound. Original BDDL readers alone do not bind no-go geometry, availability, user preferences, restore guards or compiler metadata to dynamic commitments. Existing metrics.score_step_constraints supplies lower-level geometry/action metrics, not a complete v2 semantic predicate registry.

Reissue requires a fresh occurrence identity and fresh verification, not automatically a new physical action or false-to-true transition. If fresh exact current truth satisfies the state goal for F@m, that can legitimately satisfy the new occurrence; reusing F@n's old satisfaction certificate without fresh verification is different. The production binding must preserve that distinction. If a particular event design intends a new achievement or requires an initially unsatisfied goal, its trigger and satisfaction semantics must explicitly say so and provide suitable event-time evidence. That is an unresolved task/event design choice, not a demonstrated evaluator defect or an additional universal requirement imposed here.

No additional simulator/model/provider experiments were performed for this semantic synthesis. The current learned calibration and broader readiness status must be read from their actual immutable records.


## Source-byte identities at synthesis

These working-tree file hashes bind the reviewed software, including the authorized family-scope correction; no clean-commit or complete runtime identity is asserted.

| File | SHA256 |
|---|---|
| cope_benchmark/repeated_v2/task_catalog.py | f5e1a64b72cf0257ac701118323728f1678161b46483a4b84335e6724f21d457 |
| cope_benchmark/repeated_v2/scheduler.py | cd8b5e5cfc248319c58802054400f2543731030f2904759bacf048a48ab9242a |
| cope_benchmark/repeated_v2/occurrence.py | 3a956f0e8744a5e4995934ae80d712cd33d92a04a3a56fd2dc835b380f63d0ab |
| cope_benchmark/repeated_v2/state_engine.py | 7add475d22f01a57449c07801fb095af4b1a81390578faa0d01207d6f9b8745a |
| cope_benchmark/repeated_v2/patch_contract.py | 1aeea0c4730aadf7831fe8bb9e7659b2118a0a5cd5198c4bf5bbd8e2951a41a5 |
| cope_benchmark/repeated_v2/dynamic_evaluator.py | 6272566e7c1db7d3ba9f2be826b11e5d5030f137d7f47c6fd303a33ca8fcab07 |
| cope_benchmark/task_progress.py | 48366a77d05a538c75656d7dcf5b231e68154d875d8904d10c51fc601fbe14b0 |
| cope_benchmark/metrics.py | dac0de07b639f03986b9b21cc3c8557125eaa00da1eef338816e1ec59cf2afad |
