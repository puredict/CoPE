# Verification-gated mission-state governance collision audit

Date: 2026-08-04 (Asia/Shanghai)

Primary source: [Tang et al., *Verification-Gated Agentic Mission-State
Governance for Intelligent Industrial Multi-Robot Systems*, arXiv:2606.31339v1](https://arxiv.org/html/2606.31339).

## Decision

**This is a critical novelty collision.**  It invalidates the idea that CoPE's
publishable novelty can be the combination of persistent task state, typed
repair proposals, deterministic verification, atomic commit, bounded repair,
and preservation of completed/protected work.  Tang et al. publicly specify all
of those elements in a high-level multi-robot mission-state framework.

This report supersedes the novelty nucleus in
`84_NOVELTY_COLLISION_AUDIT.md` to the extent that the earlier report treated
authorized atomic transactions over persistent commitments as a sufficiently
distinct architecture by itself.

## Full-text overlap

The paper maintains an evolving task forest and governed blackboard as
canonical persistent state.  Blackboard records include task and robot state,
world beliefs, resource locks, committed traces, proposals, verifier records
and temporary constraints.  Forest nodes have governed lifecycle states and
node-bound records include an owner.

Its proposal interface is explicitly typed and contains affected scope plus
forest/blackboard deltas.  Candidate assignments, deferrals, swaps, insertions,
diagnostics, relaxations, repairs and constraint updates cannot modify committed
state directly.  They first pass decomposed deterministic verification.

The accepted proposal atomically changes forest and blackboard.  The paper
states that no intermediate partial hierarchy/resource/trace/constraint state
is exposed.  Its locality construction closes the disturbed set over hard
couplings, restricts repair to the affected subforest, and preserves completed
nodes, protected commitments, resource locks, temporal anchors, downstream
interfaces and safety holds.  It also assumes a versioned state snapshot.

These are not loose analogies; they collide with the architecture-level phrases
CoPE was considering as its defensible nucleus.

## Differences that remain after the full-text audit

The inspected paper did not establish the following exact mechanisms:

- event-ID idempotence or exactly-once handling of duplicate delivery;
- base-revision compare-and-swap for each externally delivered interruption;
- hash-bound before/staged/after transaction receipts;
- replayable receipt chains and immutable inactive commitment lineage;
- occurrence-addressed user/task-owner replacement and cancellation events;
- learned proposal-generation evaluation on embodied manipulation.

Exact HTML searches found no match for `idempot`, `receipt`, `authorization`,
`history`, or `hash`.  Absence of those tokens is not proof that no equivalent
implementation exists.  Moreover, the paper does use a versioned snapshot,
owners, evidence-bearing lifetime-scoped constraint records, committed traces,
verification records and duplicate-assignment diagnostics, so the residual
distinction is narrower than a keyword list may suggest.

## Internal falsifier makes the residual claim narrower still

CoPE's own TX-EXEC+ experiment already shows that an independent generic
transaction executive can reproduce canonical states, directives, authority,
versions, duplicate-event no-ops, rollback, receipts, hashes and deterministic
replay on 12/12 scoped synthetic cases.  Therefore exactly-once and receipt
semantics are not uniquely expressible by CoPE either.

The remaining scientific question is not whether CoPE can implement governed
transactions.  It is whether its **occurrence-addressed minimum update
interface is a useful inductive bias for learned interruption proposals**, or
whether it offers a measurable compactness/audit benefit over capability-matched
generic governed transactions.

## Empirical boundary

Current learned evidence does not answer that question positively:

- corrected shared-envelope holdout: CoPE versus neutral typed had only 2/0
  discordance, p = 0.5;
- post-hoc corrected CoPE versus compact semantic had 4/0 discordance, raw
  p = 0.125 and Holm p = 0.25;
- retained embodied formal segment: CoPE 12/12 and neutral patch 12/12;
- TX-EXEC+ proves generic transaction equivalence offline.

Thus neither architecture uniqueness nor learned interface superiority is
currently established.

## Safe claim after collision

The most defensible prospective claim is:

> We operationalize authorized robot goal interruptions as occurrence-addressed,
> exactly-once commitment transactions and test whether a minimum typed update
> interface improves first-pass learned proposal validity and audit locality
> relative to capability-matched generic governed transactions and complete
> state regeneration.

Every verb after “test whether” must remain prospective until a fresh completed
experiment passes.  Do not claim first persistent mission-state governance,
first typed verified repair, first atomic robot-state commit, or first bounded
repair preserving completed work.

