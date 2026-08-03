# Sequential formal runner execution preregistration

Date: 2026-08-04

## Scheduled calls and dependency skips

The frozen manifest schedules at most 320 provider calls.  Event 1 is always
attempted for every substrate-eligible arm.  Event 2 is attempted only if event
1 produced and committed a valid revision-2 state.  If event 1 fails, event 2
is recorded without a provider call as
`dependency_skip_after_event1_failure`, and the sequence is a failure.  This is
necessary because fabricating an event-2 pre-state after a rejected event 1
would violate the central sequential-state requirement.  There are no retries
or repair calls, so actual provider calls are at most 320.

This clarifies “320 fixed calls” in the design documents as 320 fixed scheduled
cells / the maximum call budget, not permission to issue an invalid dependent
call merely to reach a count.

## Embodied sequence protocol

For each manifest row:

1. reset the exact assigned task-0 state;
2. construct the assigned forward/reverse prefix with the validated controller;
3. require A=true and B/C/D=false for five stable checks; otherwise mark one
   shared substrate failure and make no arm calls;
4. for each arm in the frozen counterbalanced order, reset the same state,
   reconstruct the identical prefix, and require the action-prefix hash and
   physical predicates to match the shared precheck;
5. call event 1 with revision 1, validate and commit revision 2;
6. construct event 2 only from that committed state, call and validate revision
   3;
7. execute no action for HALT, or execute only the validated final D placement;
8. score A, B, C, D predicates and stale execution, then close the environment.

Semantic failure is fail-closed: no downstream physical action.  Provider
responses never directly control low-level actions; only the shared validated
compiler can select HALT or the final object.

## Credential and integrity order

The runner checks clean commit, manifest hash, model/config, output nonexistence,
and credential presence before loading LIBERO or indexing any state.  It stops
on manifest drift, configuration drift, retry, arm-order divergence, journal
corruption, or any state outside 10--29.  The API key value is never logged.
