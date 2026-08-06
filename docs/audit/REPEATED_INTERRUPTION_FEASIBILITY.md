# Repeated Interruptions Feasibility Audit

Date: 2026-07-24

Branch: `exp/repeated-interruptions`

Reference commit audited: `570d78333ee977c8ae6de3d97120b23272c4c660`

## Decision

The installed LIBERO environment is sufficient for a versioned repeated-interruption
benchmark and for real MuJoCo Phase A correctness probes. Four `libero_10` tasks
have been preregistered as **candidates**, not declared calibration-qualified:

| Task | Independently measurable commitments | Movable target | Movable receptacle | Five states audited |
|---|---:|---:|---:|---:|
| `libero_10:0` two groceries into basket | 2 | yes | basket | yes |
| `libero_10:1` cream cheese and butter into basket | 2 | yes | basket | yes |
| `libero_10:4` two mugs onto assigned plates | 2 | yes | both plates | yes |
| `libero_10:8` two moka pots onto stove | 3, including stove-on survival | yes | no free-joint stove | yes |

The required clean OpenVLA calibration was not run because no OpenVLA checkpoint
is configured or cached on this machine. Consequently the `>=60%` clean-success
gate is unresolved, and these tasks must not be described as the final
performance-selected set. The 240-pair manifest freezes a candidate design so it
can be reviewed; Phase C/D remains blocked until Phase B qualifies every task.

## Installed suites and assets

The audit imported the installed package and instantiated real MuJoCo environments.

| Suite | Status | Tasks |
|---|---|---:|
| `libero_10` | available | 10 |
| `libero_90` | available | 90 |
| `libero_goal` | available | 10 |
| `libero_object` | available | 10 |
| `libero_spatial` | available | 10 |
| `libero_100` | registry entry is broken in this installation (`KeyError`) | n/a |

Each candidate exposes 50 initial states. States 0–4 were loaded for all four
tasks (20 real resets/state loads total), all declared free joints exist, all
initial-state SHA-256 values match the manifest, no task starts successful, and
the preregistered no-go zone excludes every audited reset EEF position.

The machine has a cached `lerobot/pi05_libero_finetuned` model, but that is not
OpenVLA and was deliberately not substituted. No clean score is inferred from
task names, another policy, scripted motion, or prior spatial-task results.

## Task-progress representation

All current physical predicates are reversible. `ProgressTracker` separately
maintains an irreversible `ever:<predicate>` episode-history ledger; this makes
a later physical regression observable without pretending that an object
placement is physically irreversible.

- Task 0: soup lifted; soup in basket; tomato sauce lifted; tomato sauce in
  basket; basket reachable; final conjunction.
- Task 1: cream cheese lifted/in basket; butter lifted/in basket; basket
  reachable; final conjunction.
- Task 4: each mug lifted; each mug on its assigned plate; both plates
  reachable; final conjunction.
- Task 8: each moka pot lifted/on stove; stove remains on; final conjunction.

LIBERO `in`, `on`, and `turnon` predicates are evaluated through the environment's
own ground-truth predicate evaluator. Lift/reachability predicates use MuJoCo
body positions and preregistered numerical thresholds. Every policy step is
logged rather than reducing progress to final task success.

## Interruption feasibility

| Event | Implementation and check |
|---|---|
| `target_object_moved` | Direct free-joint XY mutation, `sim.forward`, exact displacement check |
| `goal_receptacle_moved` | Same, on eligible tasks; task 8 is excluded from this event family |
| `temporary_no_go_zone_appears` | Versioned closed world-frame AABB; EEF point and swept-segment scorer |
| `temporary_no_go_zone_disappears` | Retires the active zone while preserving lineage |
| `user_adds_gentle_preference` | Raw translation, EEF speed, and contact-impulse-proxy ceilings |
| `tool_temporarily_unavailable` | Moves the actual designated object outside a checked accessible XYZ volume |
| `tool_becomes_available_again` | Releases the actual object at a preregistered accessible location, never a snapshot restore |

The no-go zone is a task constraint, not a physical collision obstacle. It is
communicated identically to both methods and scored from simulator truth; v1
does not add a visual MuJoCo marker. The first probe geometry placed the reset
EEF inside the AABB and was rejected. The corrected zone occupies a positive-y
route corridor and excludes all 20 audited reset poses.

The available LIBERO tasks have no semantically named hand tool. V1 therefore
uses a task-required movable object as the availability-controlled resource.
Unavailability is a real, externally checkable XYZ simulator mutation, not a prompt
string. Progress slots directly affected by that event are tagged as affected,
so they cannot be counted as silent loss.

## Remaining feasibility gates

1. Configure and record the exact OpenVLA checkpoint; run five clean states per
   candidate and require at least 60% success without inspecting recovery
   outcomes.
2. Supply exact commits and adapter factories for
   `method/cope-state-semantics`, `cope_patch`, and
   `history_augmented_full_regeneration`.
3. Confirm the v1 non-visual no-go constraint is acceptable or add a centralized,
   versioned scene marker before formal data collection.
4. Bind the formal common rollout to the main-experiment adapters; do not copy a
   second CoPE engine into this branch.

Machine-readable evidence is in
`results/repeated_interruptions_v1/feasibility_probe.json`.
