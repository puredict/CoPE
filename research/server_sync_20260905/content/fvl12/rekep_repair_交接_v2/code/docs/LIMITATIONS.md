# Assumptions and limitations (deliverable 9)

Read this before writing any claim from this repository. It states what the
current CPU implementation does and does **not** support.

## Naming

None of the baselines are the published ReKep or AgentChord systems. They are
controlled abstractions implemented here for isolation:
`fixed_program`, `path_only`, `safe_stop`, `offline_single`,
`offline_comprehensive`, `offline_budget`, `offline_enumerated`,
`template_repair`, `online_repair`. Do **not** write "beats ReKep" or "beats
AgentChord".

## Limitations table

| # | Area | Assumption / limitation | Consequence for claims |
|---|---|---|---|
| 1 | Event space | Predicates are a **fixed enumeration** of 3 world predicates (`obstacle_present`, `object_slipped`, `target_relocated`). There is no open-set event discovery. | "Novel" means a **novel composition of known predicates**, never an unforeseen event class. |
| 2 | Operator library | 9 typed operators, fixed at design time. Synthesis composes them; it does not invent new ones. | The claim is compositional coverage, not unbounded generality. |
| 3 | Abstract model | Operator preconditions/effects are hand-written booleans. Their fidelity to the concrete world is only checked by the rollout, not proven. | Symbolic goal satisfaction is necessary, not sufficient — hence the independent rollout re-verification. |
| 4 | Rollout verifier | Uses the same kinematic model as the environment (no model error, no sensor noise inside the rollout). It is a *predictor with a perfect model*. | Rejection/acceptance rates would degrade under model mismatch; not yet measured. |
| 5 | Dynamics | Kinematic point robot, first-order integration, no inertia, no contact physics, no true grasping. `theta` is one scalar shared by end-effector and held object. | Results transfer as a *mechanism* demonstration only, not as manipulation performance. |
| 6 | Object slip | Regrasp completes on proximity (< 0.05) with probability 1. No gripper state, grasp quality, or failure. | "Reacquire" measures reaching the drop point, not reliable regrasp. |
| 7 | Latching | Both online and offline latch handled predicate combinations so a persistent predicate does not re-trigger. | Necessary for termination; means a *recurring* disturbance of the same combination is handled once, not continuously monitored. |
| 8 | Events during repair | Mid-repair events are **deferred** and recorded (`deferred_events`), not merged or replanned. | We do not yet support requirement merging into a running repair. |
| 9 | Detection | Ground-truth predicates by default. `NoiseModel` supports delay / false pos / false neg but is **not** enabled in the reported comparisons. | Robustness-to-detection-error is untested in the headline numbers. |
| 10 | Seeds | Dynamics and events are deterministic; different seeds give identical episodes. | **Multi-seed statistics are not yet meaningful.** No confidence intervals should be reported. |
| 11 | Scenes | Each result is a single hand-constructed scene per condition, not a distribution. | No statistical claim of any kind is currently supported. |
| 12 | Offline baselines | Branch bodies are compiled with the *same* planner, but without runtime geometry, and carry no restore contract (by construction of the paradigm). | The offline gap has two causes — coverage and runtime verification — which `coverage_experiment.py` separates. Do not attribute all of it to coverage. |
| 13 | Provenance metric | `continuation_linked_provenance` structurally favors methods that carry a continuation. | Report it separately; use `event_attribution` / `policy_attribution` for cross-method comparison. |
| 14 | Theorem 1 | Proved for nonempty sets with `inf`. The threshold corollary holds **for fixed weights**; the floor is not uniform over weights. | Never write "no choice of penalty weights can succeed" without bounding weights away from 0. |
| 15 | Theorem 1 scope | Establishes irreducible *simultaneous-objective* conflict under a fixed-mode model. | It does **not** prove program repair is universally superior, and ordered repair's total cost floor is not zero. |
| 16 | Feasibility filter | The pre-rollout screen is a cheap terminal-handoff heuristic; the rollout is the real check. | Call the screen a heuristic, not verification. |
| 17 | Scale | 2D, single nominal stage in most scenes (two in the repeated-repair test). No ReKep solver, no keypoints, no OmniGibson. | No claim about real manipulation tasks is supported yet. |

## What the current evidence does support

1. Runtime **synthesis** (not template lookup) of repair programs from atomic
   typed operators, under event-conditioned goals — `run_trace.py`,
   `tests/test_synthesis.py`.
2. **Sequential verification** distinguishing two symbolically-equal plans by
   rolling them out against real geometry — `rollout_traces.py`.
3. A **two-axis** offline/online comparison: coverage saturates (3→7 branches
   buys nothing) while runtime verification does not — `coverage_experiment.py`.
4. **Parity on anticipated single events** — `compare_known_event.py`.
5. State-machine correctness: atomic transitions, unique repair ids, restoration
   gating, bounded fallback, two repairs per episode — `tests/`.

## What it does not support yet

Statistical claims, robustness-to-noise claims, real-robot or simulator claims,
open-set event claims, or any comparison to published systems.
