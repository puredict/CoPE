# Zero-provider feasibility execution plan

Audited 2026-09-06 against local integrated HEAD 688b7eb3a91fdf5229ea2cda87e9a33f85566fe6. No production runtime or catalog source changed. The reset sweep below was authorized and executed; all further event experiments remain unexecuted.

## Completed reset sweep

The existing tools.audit_repeated_feasibility.audit API ran on fvl12 with installed LIBERO/MuJoCo, CUDA_VISIBLE_DEVICES='', cameras/renderers disabled and no provider or policy. Its TASK_DEFINITIONS already contains exactly task IDs 0,1,4,8; the existing manifest contains the same tasks. The API examines state IDs 0..4.

[Actual receipt](reset_feasibility_20260906T171329Z_618e9be2/RECEIPT.txt), [unmodified raw result](reset_feasibility_20260906T171329Z_618e9be2/RESET_PROBE_RAW.txt), [exact execution command](reset_feasibility_20260906T171329Z_618e9be2/EXECUTION_COMMAND.txt), and [copy verification](reset_feasibility_20260906T171329Z_618e9be2/COPY_VERIFICATION.txt) are preserved locally and remotely. Receipt SHA256: d096c432d8a20c1fe0cc222bd7f99ac84b760f1e17fed556594fab6d981a3190. Raw SHA256: 4ba6533cc965d6ecad7b368134c078e287e9d7792f524cf5501a902310aaf667.

All four candidate gates returned true: declared free joints exist, every task has five audited states, each has at least two declared commitment predicates, and the existing no-go AABB excludes every reset EEF. All 20 state hashes match STATE_HASHES.csv. No complete original goal was initially satisfied. Torch remained CUDA-uninitialized. Event injections, safe-event certificates and milestone-preservation certificates: zero.

“Two declared commitment predicates” is a source count, not empirical independence or preservation. Task8's third declaration is the stove-on clause, already in the BDDL initial conditions. Reset EEF exclusion from one box does not establish a collision-free route or attainable post-event goal.

The raw helper retains an obsolete clean_calibration block declaring 0.60 and “checkpoint not configured locally.” It was explicitly ignored: this v1 metadata does not describe the production VLA gate, the separately audited repeated-v2 calibration, or the v2 selection rule.

The remote checkout reports c0308c1fc13036ef34983dd07397744f659cb417. All four bound helper/manifest files match local integrated source bytes; this does not claim whole-tree identity.

## Existing executable entry points

The completed run called the following API, wrapped only for exclusive publication and provenance:

~~~python
from pathlib import Path
from tools.audit_repeated_feasibility import audit
result = audit(Path("manifests/repeated_interruptions_v1.jsonl"))
~~~

The existing CLI equivalent is:

~~~bash
env CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 \
  MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
  LIBERO_CONFIG_PATH=/home/lijingsu/.libero \
  scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  tools/audit_repeated_feasibility.py \
  --manifest manifests/repeated_interruptions_v1.jsonl \
  --output /absolute/new/unique/RESET_PROBE_RAW.txt
~~~

There is no reason to rerun the completed sweep. The old CLI can overwrite its output; the executed wrapper instead created a unique directory and used exclusive publication. The exact command is retained with the receipt.

The existing opt-in physics smoke can run without a provider, but covers only task1/state0:

~~~bash
env COPE_RUN_LIBERO_SMOKE=1 CUDA_VISIBLE_DEVICES='' \
  PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
  scripts/run_project_env.sh /home/lijingsu/vla/.venv/bin/python \
  -m unittest tests.repeated_v2.test_phase3_simulator_smoke
~~~

The old experiments/repeated_interruptions.py --phase correctness runner intentionally uses CorrectnessNoOpAdapter, fixed-step v1 scheduling and two historical methods. It cannot serve as the learned-policy pilot or v2 semantic-trigger qualification. Legacy prefix scripts use LiberoOracleSkillController; they are not proposed as substitute execution.

## Live task-specific capabilities

These are actual source/initialization capabilities, not supported-event declarations.

| Task | Actual movable targets | Actual movable goal receptacle | Original goals |
|---|---|---|---|
| 0 | alphabet_soup_1_joint0; tomato_sauce_1_joint0 | basket_1_joint0 | Two distinct objects in basket |
| 1 | cream_cheese_1_joint0; butter_1_joint0 | basket_1_joint0 | Two distinct objects in basket |
| 4 | porcelain_mug_1_joint0; white_yellow_mug_1_joint0 | plate_1_joint0; plate_2_joint0 | Each mug on its specified plate |
| 8 | moka_pot_1_joint0; moka_pot_2_joint0 | None | Two pots on stove; stove remains on |

Task8's instantiated free-joint list contains only the two moka pots. Its stove is a fixture constructed with joints=None; the XML contains a button hinge. Free-joint stove relocation is unavailable. The old manifest correctly omits goal_receptacle_moved for task8. Another semantic grounding variant requires its own definition and evidence; it cannot be inferred from the broader v2 family name.

## Minimal next physical-effect checks

No new planner, reasoner, oracle controller or runtime architecture is needed to test existing simulator primitives. A small one-off wrapper can call these exact APIs in isolated ControlEnv instances and record actual outcomes. A successful primitive does not itself establish v2 event support.

~~~python
from cope_benchmark.interruptions import (
    LiberoInterruptionContext, InterruptionEvent, apply_interruption,
)
from cope_benchmark.task_progress import (
    get_task_definition, ProgressTracker, LiberoStateView,
)
from libero_experiment_core import validate_free_joint, sim_from_env

context = LiberoInterruptionContext(env, initial_observation)
event = InterruptionEvent.from_dict(exact_selected_legacy_event_record)
before_progress = tracker.sample(LiberoStateView(env), policy_step).to_dict()
application, fresh_observation = apply_interruption(
    context, event, policy_step=policy_step,
)
after_progress = tracker.sample(LiberoStateView(env), policy_step).to_dict()
~~~

Here env, tracker, exact_selected_legacy_event_record and policy_step must come from the actual saved task/state and recorded candidate manifest. This is an API map, not a complete qualification driver. Hidden application/ground-truth records cannot later be forwarded to ordinary method prompts or policy observations.

Retain exact payload/state hashes, qpos/qvel before/after, simulator time and explicit environment-step counters, affected joint slice, grasp/contact evidence, before/after predicates, observation refresh path and failures. Check only intended coordinates or constraint state changed. No-go/preference events should leave physical qpos/qvel unchanged. XY displacement should preserve untouched z/orientation coordinates. Test duplicate/lifecycle rejection only where the library implements it.

The existing refresh helper can fall back to env.step(dummy_noop) if observation getters fail. apply_interruption then rejects consumed_noop_env_step, but that control has already happened. Record the failure; do not silently undo or omit it. A strict probe may forbid env.step during injection and use the already verified force-update observation path. Actual timestamps/state still need recording.

| V2 family | Existing primitive / candidate task scope | What a live zero-provider probe can establish | Still unqualified |
|---|---|---|---|
| TARGET_OBJECT_DISPLACED | v1 target_object_moved; tasks 0,1,4,8 | Exact requested XY effect, unrelated state retained, fresh observation, zero injection controls | Collision/stability, safe pose, held-object guard, recoverability, semantic trigger, completed-milestone preservation |
| GOAL_RECEPTACLE_OR_GROUNDING_CHANGED | v1 goal_receptacle_moved; tasks 0,1,4 | Basket/plate movement primitive and exact effects | Safe alternative grounding, remaining-goal feasibility, any task8 variant |
| TEMPORARY_NO_GO_APPEARS / CLEARS | v1 constraint activation/retirement; candidate geometry for all four | Same zone/version, appear-before-clear, no physical mutation, reset EEF outside | Current whole-arm/contact exclusion, legal route, trigger boundary, recoverability, fresh clearance proof |
| USER_ADDS_PERSISTENT_PREFERENCE | v1 handle-gently activation; all four manipulate objects | Positive bounds, persistent constraint record, no simulator mutation | Grounded preference meaning, cross-skill relevance, actual policy compliance |
| TOOL_OR_TARGET_TEMPORARILY_UNAVAILABLE / AVAILABLE_AGAIN | v1 removal/release of listed target joints; all four | Exact XYZ, outside/inside legacy box, paired identity, explicit release instead of snapshot restore | True accessibility, physical containment/safety, alternative plan, fresh grasp/precondition revalidation |
| USER_REPLACES_ACTIVE_GOAL | v2 pure utterance injection; no qualified task live binding | Schema/public-envelope/pure-state tests only today | Authentic alternative goal, scope, occurrence retirement, updated-task feasibility |
| USER_CANCELS_ACTIVE_GOAL / USER_REISSUES_RETIRED_GOAL | v2 pure utterance injection; original families known | Schema/lifecycle tests with labeled fixtures only today | Grounded cancellation, retained constraints/progress, exact reissue identity, live trigger evidence |

Existing fixed displacements/release coordinates are reproducible candidates, not certified safe poses. The v1 no-go payload explicitly sets physical_collision=false and visual_marker=false: this is a normative constraint, not a spawned obstacle. Availability inside a box is only the implemented guard, not proof of reachability or continuation.

The v1 physical injector has no general held-object guard. v2 inject_event checks the supplied world.held_object against forced_external_displacement, but a true held-object detector remains necessary. The pure guard cannot authenticate its input.

## V2 boundary and semantic checks

repeated_v2/events.py exposes inject_event(world=..., public_payload=..., hidden_effect=...) and complete_event_injection(pending, FreshObservation). These pure contracts do not move LIBERO objects, invoke a detector or obtain observations. safe_positions is caller-supplied data, not an independent collision certificate. The production RuntimeEnvironment.inject bridge remains unbound.

Existing tests/repeated_v2/test_events.py, test_evidence.py and test_scheduler.py cover synthetic contracts without a provider. Passing them cannot clear a task's event_feasibility records.

A later empirical check may replay a completed clean-calibration trace's exact recorded environment controls from the same initial state to a naturally reached prefix where one placement is true and another remains pending. This needs no new provider/VLA call. Validate reproduced observations/progress; retain divergence or absent qualifying prefixes. That state can support an isolated injection/preservation probe. It is not learned closed-loop recovery, and replayed post-event controls must not be labeled fresh VLA behavior. An oracle-generated prefix or simulator truth cannot substitute for production public observations.

Without an observed completed placement, a preservation check is vacuous. Task8's already-on stove alone does not establish two independently achieved placement milestones.

## Unchanged catalog and formal admission rules

Current v2 requires states0..4, clean policy seeds101/131, horizon260 and ten terminal records per task; measured learned nonprivileged policy; matching state/checkpoint/protocol hashes; clean success rate in [0.40,0.95]. Formal seeds stay11/29/47. At least8 and at most10 eligible tasks are required. Four tasks passing reset checks or completing40 clean cells cannot satisfy minimum8.

Structural checks require two independently verified distinct milestone predicates, a verified preservable milestone, changeable grounding and cross-skill requirement or persistent preference, with evidence references. Aliases, original/alternative goals, safety constraints, evaluator/compiler metadata and source bytes have separate requirements.

As implemented, task_catalog.py:253-279 also demands every task declare all10 families, each with passed Boolean/evidence_refs/covered_state_ids=[0,1,2,3,4], named semantic predicate/physical guard, legal0..260 trigger window/gap>=10, and evidence-backed pose/region/entity for six physical families. Selection requires every family passed=true. This all10-per-task strengthening conflicts with the user's explicit task-specific-support instruction. Do not populate unsupported entries to satisfy it. No threshold or catalog value was changed here.

The generator independently demands all10 supported families; MasterSchedule requires exactly8 events including both temporary pairs, preference, retirement/reissue and a grounding variant. VLA runs use the first4. CLI pilot currently applies full catalog admission. A subset pilot needs an explicit scoped input/admission seam rather than falsified support or modified formal minima.

This report records one completed reset/source sweep. Further live physical-effect checks are proposed only; no full safe-event, structural or learned-recovery certification was issued.
