# Controller privilege card

Controller: `LiberoOracleSkillController`

Qualification target: LIBERO-10 task-1 basket pick-and-place only.

## Explicit interface

- `pick_and_place(object_name, target_region_name)` exposes skill arguments.
- `pick_object(object_name)` returns a `HeldObjectCheckpoint`.
- `place_held(checkpoint, target_region_name)` continues a held-object skill.
- `return_held_to_start(checkpoint)` and the frozen local-stage operator dispose
  of an invalidated held object before switching commitments.

## Privileged inputs

| Capability | Access | Consequence |
|---|---|---|
| Object identity | Oracle symbolic name | No language grounding is tested |
| Region identity | Oracle symbolic name | No target grounding is tested |
| Object/region position | Simulator geometry | Position-only oracle control |
| EEF position | Simulator observation | Closed-loop Cartesian control |
| Grasp predicate | Private simulator check | Privileged grasp verification |
| In-region predicate | Private simulator predicate | Oracle outcome scoring |
| Event timing | Deterministic phase boundary | No event detector/latency test |
| Patch operation | Oracle-selected | No provider inference test |
| Initial reset | Assigned state index 0--4 | Development layouts only |
| Checkpoint | Deterministic action replay plus hashes | Not perception-derived |

## Excluded capabilities

- no learned policy;
- no RGB-to-action or language-to-action inference;
- no provider call;
- no force, calibrated collision, or human-safety measurement;
- no narrow-compartment insertion qualification;
- no evidence for event interpretation or repair synthesis.

## Geometry and recovery boundary

Basket transfer, exact return, and local staging use privileged simulator
positions. Local staging is fixed at 75% of the basket-to-original-pose vector
and verified outside the basket. This is an oracle repair-compiler primitive,
not a learned motion planner. The task-5 caddy insertion failure remains out of
scope and prevents cross-target generalization claims.

## Access/accounting labels required per episode

Every row must state: `controller_privilege=simulator_geometry_oracle`,
`learned_policy_used=false`, `provider_called=false`,
`oracle_operation_selection`, `oracle_geometry_used=true`,
`reset_state_index`, `shared_init_container_loaded=true`,
`reserved_state_indexed=false`, `checkpoint_access`, and the applicable action/
simulator hashes.

## Allowed claim
