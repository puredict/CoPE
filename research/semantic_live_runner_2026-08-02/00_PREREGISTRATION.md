# Live semantic runner integration preregistration

Date frozen: 2026-08-02 (Asia/Shanghai)

Pre-implementation parent: `450f3ee7db5d65d84bcbe899178761c17f4a8ba6`

## Question

Can an already-consumed LIBERO-10 task-1 physical checkpoint produce a real
production predicate packet that is consumed by one atomic semantic runner,
while native Oracle FSR-PC and Oracle CoPE receive byte-identical recovery
input and converge through the same full-state-v2 validator/compiler without
changing simulator state or emitting an action?

This is a live CPU simulator integration preflight. It is not learned-provider
evidence and it does not execute a post-event recovery policy.

## Frozen cases

`01_CASES.csv` assigns states 0--4 to both `replace_pending_goal` and
`cancel_pending_goal`, for ten rows. These states were consumed during earlier
development. States 25--49 remain locked and must not be read.

For each state, the method-independent prefix is:

1. reset the exact LIBERO-10 task-1 initial state;
2. execute the common Oracle skill to put `cream_cheese_1` in
   `basket_1_contain_region`;
3. verify the predicate for five additional simulator steps and verify
   `butter_1` remains outside;
4. freeze the exact action-prefix digest and MuJoCo qpos/qvel digest;
5. encode the current RGB observation and produce a non-test predicate packet
   by calling registered LIBERO predicates.

## Frozen invariants

Every assigned row must show:

- the physical milestone is reached and stable for five steps;
- packet `source_kind=live_libero_eval_predicate`, `test_only=false`, and its
  task/event/RGB/simulator-state/producer bindings validate;
- the production validator metadata is non-fake and consumes the packet,
  returning true for the completed commitment and false for the pending one;
- Oracle FSR-PC and Oracle CoPE use the same canonical RecoveryInput bytes and
  input hash;
- the CoPE typed transition is accepted, provider-free, and materializes
  independently into full-state-v2;
- native and materialized full states, SHA-256 digests, and compiled directives
  are identical;
- both pass the same event-bound validator;
- simulator-state hash and controller action count are unchanged by both
  semantic computations;
- no post-event controller action, provider call, GPU, or reserved-state read
  occurs.

The runner must reject any state outside 0--4 and use output-create semantics.
Focused tests must also prove state-lock rejection, live packet binding, and
action/simulator non-mutation accounting.

## Decision rule

The live X04 integration preflight passes only if all ten rows pass, focused
tests pass, the existing 4/4 independent materialization preflight remains
unchanged, the 123-case corruption audit remains 123/123, and the full
repository regression is clean.

A pass may upgrade X03 live packet production and the X04 oracle CPU/live
integration boundary. It does not demonstrate learned CoPE performance,
closed-loop recovery, or superiority over FSR-PC.

State 25/26 stays locked after this result unless a separate oracle-pilot
readiness audit confirms all of the following from a clean committed tree:

1. production live packet observed;
2. common full-state-v2 path observed;
3. task-1 semantic config and exact reserve manifest consumed by the runner;
4. qualified common Oracle controller parameters are pinned;
5. reset/prefix provenance and output destinations are collision-safe.

## No-retuning rule

Cases, objects, event types, five-step stability rule, packet schema, and
acceptance criteria cannot change after results are observed. A defect requires
retaining the original output and issuing a versioned correction.
