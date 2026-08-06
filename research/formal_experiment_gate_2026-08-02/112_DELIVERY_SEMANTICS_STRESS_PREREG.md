# Delivery-semantics and crash-boundary stress preregistration

Date frozen: 2026-08-04 (Asia/Shanghai)

## Question

Are duplicate/out-of-order rejection and crash-safe exactly-once effects unique
to the CoPE typed carrier, or do they arise from event binding, version checks,
staging and publication shared by capability-matched representations?

## Scope

This is a credential-free semantic systems test.  It uses one public synthetic
two-event basket sequence and no LIBERO state.  It cannot establish learned
generation, embodiment, physical safety or novelty.

## Arms

1. CoPE typed minimum update;
2. neutral JSON-path transaction;
3. governed affected-scope delta;
4. complete semantic-state regeneration.

Each arm receives its own oracle-correct frozen proposals for the same event
and base state.  All use the shared canonical transition validator.  A rejected
delivery leaves both logical and typed state unpublished.

## Assigned schedules

1. nominal event 1 then event 2;
2. immediate duplicate event 1 after publication;
3. delayed duplicate event 1 after event 2;
4. event 2 delivered before event 1, then normal recovery;
5. two conflicting event-2 proposals from the same base, first writer wins;
6. crash before validation, followed by retry;
7. crash after successful staging/validation but before publication, followed
   by retry;
8. crash after publication but before acknowledgement, followed by retry.

The frozen denominator is 8 schedules x 4 arms = 32 schedule-arm cells.

## Endpoints and gate

PASS requires:

- 32/32 cells reach the schedule-specific canonical final state;
- exactly two publications per cell and no duplicate physical directive;
- every duplicate, stale, out-of-order or losing conflict delivery is rejected
  without changing the published state;
- post-stage/pre-publish crash exposes no staged state and the retry publishes
  exactly once;
- post-publish/pre-ACK retry does not publish again;
- CoPE typed revision/hash continuity remains synchronized with logical state;
- no caller-state mutation on any rejection;
- zero provider calls, simulator indexing and credentials.

If all arms pass, exactly-once behavior is attributed to the shared transaction
protocol rather than CoPE's operation labels.  If only CoPE passes, the first
failing layer must be localized before any uniqueness claim; an intentionally
weaker baseline does not count.

