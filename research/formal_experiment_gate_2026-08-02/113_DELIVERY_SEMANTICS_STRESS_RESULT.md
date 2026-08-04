# Delivery-semantics and crash-boundary stress result

Date: 2026-08-04 (Asia/Shanghai)

## Decision

**PASS for all representations; CoPE-specific exactly-once attribution is
falsified in this scope.**  CoPE, neutral JSON path, governed delta and complete
state regeneration all produced the same published effects under duplicate,
delayed, out-of-order, conflicting and simulated crash-boundary delivery.

## Frozen evidence

- runtime commit: `9cd97f48f14a5448870308153c3ce514faa0c7de`;
- schedules: 8;
- arms: 4;
- assigned schedule-arm cells: 32;
- passed: 32/32;
- publications: exactly 2 in 32/32;
- semantic directive count: exactly 2 in 32/32;
- cross-arm final-state equivalence: 8/8 schedules;
- rejected duplicate/stale/conflicting deliveries: 20 total;
- caller-state changes on rejection: 0/20;
- simulated crash markers: 12;
- validated stages discarded before publication: 4/4;
- typed/logical revision synchronization: 32/32;
- provider calls: 0;
- simulator states indexed: 0;
- full regression: 575/575 passed.

## Schedule outcomes

| Schedule | Expected special behavior | All four arms |
|---|---|---:|
| nominal | two publications | PASS |
| immediate duplicate | duplicate event 1 rejected | PASS |
| delayed duplicate | old event 1 rejected after event 2 | PASS |
| out of order | event 2 rejected before event 1, then recovery | PASS |
| same-base conflict | first event-2 writer commits; losing writer rejected | PASS |
| crash before validation | retry commits once | PASS |
| crash after stage | validated stage discarded; retry commits once | PASS |
| publish before lost ACK | retry rejected; no second publication | PASS |

## Causal interpretation

The representations differ substantially in generated carrier shape, but every
arm is bound to the same immutable event, read revision and canonical
validator.  Publication occurs only after a complete candidate exists.  Once a
publication advances the state and active chain tip, replayed or competing
events fail the shared revision/target checks.  That common protocol is
sufficient for the observed exactly-once effects.

Therefore the paper must not attribute duplicate suppression, out-of-order
rejection, first-writer-wins or stage-before-publish atomicity to CoPE operation
labels.  CoPE can expose these semantics compactly and audit them through typed
receipts, but a capability-matched generic transaction or complete-state arm
can obtain the same behavior.

## Important limitation

The crash locations are deterministic **in-process publication simulations**:
the experiment discards a returned staged state or retains a published state
before retry.  It does not terminate an operating-system process, corrupt a
file, exercise an fsync/WAL implementation, or rebuild state from a durable
journal after power loss.  The result establishes transition semantics, not
storage durability.  A real crash-recovery claim would require a separately
preregistered subprocess/append-log experiment with fault injection and cold
restart.

## Submission effect

This negative causal result is useful but further narrows novelty.  The only
remaining method discriminator is learned proposal factorization and measurable
locality/audit cost.  If CoPE does not beat both neutral patch and the governed
control in a completed learned sequence study, the method-superiority route is
closed.

