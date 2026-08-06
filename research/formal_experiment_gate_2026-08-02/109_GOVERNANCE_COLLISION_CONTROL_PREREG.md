# Governance-collision control capability-gate preregistration

Date frozen: 2026-08-04 (Asia/Shanghai)

## Motivation

Tang et al. (arXiv:2606.31339v1) expose a closer control than the existing
full-state and generic JSON-path arms: a typed governed proposal with affected
scope and forest/blackboard deltas, admitted only after deterministic
verification and atomic commit.  A future CoPE comparison must show that such a
control is capable of expressing every correct sequential interruption outcome
before learned failures can count.

## Assigned cases

Use the four public, simulator-free cases in
`manifests/sequential_persistence_gate_v2.csv`:

- forward and reverse completed-prefix orientations;
- replace then cancel;
- replace then replace.

Each arm consumes two dependent events.  Event 2 must be constructed from the
committed event-1 state.  No LIBERO initial state, provider credential, model
call or GPU is allowed.

## New control contract

The `governed_delta` proposal contains:

- schema version, event ID and read revision;
- generic proposal type `repair`;
- explicit affected stable-node scope;
- complete after-records for changed forest commitment nodes;
- blackboard deltas for current goal, remaining plan and restorations.

It must not emit CoPE operation names, patch IDs, receipts, hashes or trusted
state/evidence versions.  Trusted code validates scope, revision and event
binding; stages the generic deltas; supplies trusted metadata; runs the same
canonical sequential validator; and only then publishes an accepted result.

## Arms and denominator

Five arms are capability checked on four full sequences:

1. CoPE typed minimum update;
2. neutral JSON-path transaction;
3. FSR-PC complete state;
4. full remaining-task replan;
5. Tang-style governed delta operationalization.

The fixed denominator is 20 sequence-arm cells and 40 transitions.

## Gate

PASS requires all of the following:

1. 20/20 cells finish revision path 1 > 2 > 3;
2. every event-2 before hash equals its event-1 after hash;
3. all five arms have the same final canonical state and directive per case;
4. governed-delta negative tests reject stale revision, event mismatch, scope
   mismatch, completed-record mutation and omitted changed nodes without caller
   mutation;
5. static/source tests show the governed proposal has no CoPE operation or
   receipt fields;
6. provider calls, simulator state indexing and credentials are zero.

Any failure is an interface failure and blocks admission to a future learned
comparison.  A PASS proves capability parity only, not novelty, learned
superiority or independent implementation.

