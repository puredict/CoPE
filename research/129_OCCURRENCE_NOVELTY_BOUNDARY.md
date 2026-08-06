# Occurrence identity novelty boundary

Date: 2026-08-04

## Decision

**Do not claim that occurrence IDs, event histories, or lifecycle records are
new.** The defensible residual question is empirical and robot-specific:
whether a compact occurrence-addressed minimum-edit interface improves
first-pass learned interruption updates while preserving prior commitment
lifetimes.

## Primary-source audit

### Mission-state governance collision

[Tang et al. (2026)](https://arxiv.org/html/2606.31339) already maintain an
evolving task forest, governed blackboard, node-anchored execution state,
typed proposals, deterministic verification, atomic commit, completed-work
protection, and factory inspection/rework loops. Exact full-text searches found
no `occurrence`, `identifier`, or `node ID` terminology, but absence of those
words is not evidence that unique task-node instances are unsupported. The
paper remains a hard collision for architecture/assurance novelty.

### Event and commitment formalisms

The [Event Calculus reference treatment](https://www.sciencedirect.com/science/article/pii/S1574652607030179)
separates event occurrences on a time line from fluents that those events
initiate or terminate. Repeated initiation of the same fluent is therefore
foundational action/change representation, not a CoPE invention.

[Chesani et al.](https://link.springer.com/article/10.1007/s10458-012-9202-0)
formalize creation, monitoring, and lifecycle operations for commitments with
events, data, and metric time. This is direct prior art against a broad claim
that event-addressed commitment lifecycles are new.

Workflow research likewise separates a task name from a task instance and a
workflow case; the primary
[workflow-mining survey](https://www.sciencedirect.com/science/article/abs/pii/S0169023X03000661)
explicitly models events with task and optional task-instance identity. A
recurring activity creating a new work item is standard workflow semantics.

## What the new result actually adds

The CoPE implementation exposed a concrete robotics benchmark failure:
object-derived IDs cannot represent an authorized return to the same grounded
goal without overwriting history. The occurrence-addressed development schema
fixes that failure, and five matched carriers can express it. This yields:

1. a precise recurring-commitment interruption case for robot evaluation;
2. a minimum-change output contract that distinguishes predicate arguments
   from commitment occurrence identity;
3. negative tests for stale, wrong-target, duplicate, reactivation, and
   history-omission errors;
4. an embodied canary showing the sequence is executable on task 7, tempered by
   a later controller failure on state 2.

It does **not** establish that CoPE labels, unique IDs, event sourcing,
verification gates, or persistent task forests are novel.

## Defensible paper language

Safe prospective claim:

> We study occurrence-sensitive commitment editing for robot interruptions:
> when an already superseded grounded goal is authorized again, the recovery
> interface must create a new temporal commitment occurrence while preserving
> the earlier record. We test whether a compact typed delta improves first-pass
> generation relative to representation-matched generic and governed deltas.

Unsafe language:

- “first persistent mission-state architecture”;
- “first event-addressed commitment lifecycle”;
- “unique task IDs are our contribution”;
- “exactly-once recovery is specific to CoPE”;
- “task-7 results establish cross-task method generality.”

## Submission consequence

Occurrence addressing narrows the project to a potentially publishable
benchmark/interface contribution, but it does not by itself reverse the
method-paper NO-GO. The decisive evidence is still learned first-pass success
against both neutral and governed occurrence-aware controls, followed by
physical replication with a qualified controller. Current task-7 physical
development stops short of the latter.
