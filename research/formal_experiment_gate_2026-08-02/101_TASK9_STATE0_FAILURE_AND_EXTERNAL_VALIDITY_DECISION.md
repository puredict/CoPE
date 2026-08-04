# Task-9 state-0 failure and external-validity decision

Date: 2026-08-04 (Asia/Shanghai)

## Decision

The first assigned task-9 state0 canary failed its physical prefix. Stop task 9
and do not open states 1--49. The variable-arity semantic protocol remains
valid unit evidence, but task 9 contributes no embodied or confirmatory result.

## Retained result

Create-only directory:
`research/task9_cross_predicate_2026-08-04/state0_canary_v1`.

- initial contract: pass;
- microwave open: true;
- both mug-in-heating predicates initially false;
- grasp and lift phases completed;
- `descend_to_release`: 60-step bound reached with 0.068545452 m final
  end-effector error;
- final `in(white_yellow_mug_1, microwave_1_heating_region)`: false on 5/5
  checks;
- failure: `target_predicate_false`;
- actions: 322;
- provider calls: 0;
- task-9 states 1--49 indexed: 0;
- task-6 states opened after stop: 0;
- task-1 forbidden states indexed: 0.

Because the prefix failed, the two semantic events were correctly skipped and
issued no controller actions.

## Interpretation

The task-9 BDDL and semantic design were not the failure source. The existing
privileged controller could not reach the heating-region release pose through
the microwave geometry within its frozen motion bound. This is a substrate
failure analogous to, but mechanically distinct from, the task-6 plate failure:

- task 6/task 4 exposed missing held-object XY compensation for `on`;
- task 9 exposes collision/approach limitations for fixture insertion.

The earlier basket task-0 10/10 result therefore qualifies that specific
object/receptacle family. It does not qualify a generic oracle robot executor
across LIBERO-10.

## Consequence for the paper

Do not claim:

- physical multi-task generalization;
- a generally qualified privileged executor;
- that semantic success automatically compiles to executable recovery on
  arbitrary fixtures;
- task 6 or task 9 as positive replications.

Allowed negative result:

> Two statically suitable, previously unused task identities were rejected by
> preregistered state-0 canaries because the privileged executor failed their
> distinct geometric contracts, while the commitment-transition unit protocols
> remained valid.

This is useful reviewer-facing evidence that the benchmark does not hide
substrate failures or cherry-pick only successful identities. It does not
strengthen the primary efficacy claim.

## Next identity policy

Further fresh LIBERO-10 state spending is paused. The remaining clean tasks
either require unqualified articulated control or lack a two-event commitment
inventory. Any next physical replication must choose one of two honest paths:

1. use an already exposed but mechanically qualified caddy/basket identity and
   label it engineering replication, not fresh confirmation; or
2. qualify a new general controller on a separate development suite before
   preregistering another fresh identity.

Neither path authorizes task-1 state33, task-1 states34--49, task-6 states1--49,
or task-9 states1--49.

