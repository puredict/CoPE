# CoPE novelty-collision audit

Date: 2026-08-04

Scope: narrow primary-source audit of the nearest claims, current through the
date above.  This is not yet an exhaustive systematic review; full-paper claim
tables are still required before submission.

## Bottom line

The broad claim **"repair a robot plan locally instead of replanning from
scratch" is not novel enough**.  CoPE should not use that sentence as its main
novelty claim or any "first" claim.

The potentially defensible nucleus is narrower: **represent interruption
recovery as an authorized, atomic and auditable transaction over a persistent
commitment ledger, preserving completed physical facts and historical inactive
commitments across dependent sequential interruptions**.  Even this must be
supported by the locked generic JSON-path neutral comparison; architecture
alone does not show that typed `Override`/`Expire` semantics add value.

## Closest collisions

1. [InstructFlow (NeurIPS 2025)](https://proceedings.neurips.cc/paper_files/paper/2025/hash/03cfff3eccb29aa15f76e9bcee3d1be7-Abstract-Conference.html)
   induces symbolic constraints from execution failures and propagates them
   through a hierarchical instruction graph for targeted code/subgoal repair
   without full regeneration.  This directly defeats a generic "symbolic local
   repair rather than regenerate" novelty claim.  CoPE must distinguish
   persistent commitment identity, authorization, atomic versioned receipts,
   idempotence and stale-commitment prevention—not merely locality.

2. [Intelligent Execution through Plan Analysis](https://arxiv.org/abs/2403.12162)
   explicitly stores planning-time opportunities and repairs execution plans
   rather than replanning from scratch.  It is a direct conceptual predecessor
   for plan repair versus replanning, although its stored opportunity model is
   different from CoPE's interruption-time commitment transactions.

3. [REFLECT (CoRL 2023)](https://proceedings.mlr.press/v229/liu23g.html)
   summarizes multisensory execution experience, explains failures with an LLM
   and guides a language planner to generate correction plans.  CoPE cannot
   claim first LLM-guided robot failure explanation/correction.  Its distinction
   is state-transition assurance, not failure diagnosis.

4. [PLanAR (2026 preprint/project)](https://planar-robot.github.io/)
   uses object predicates, action schemas, symbolic plans, stepwise effect
   verification, task-state updates and replanning under execution deviation in
   real robot long-horizon tasks.  It raises the empirical bar: CoPE's current
   one-task LIBERO oracle-controller design is weaker on open-world grounding and
   cross-task embodiment.  CoPE's non-overlap is transaction semantics over
   persistent commitments rather than closed-loop perception/replanning.

5. [RePlan-Bot (2026 preprint)](https://arxiv.org/abs/2605.25851)
   performs multi-level continuous replanning with a high-level auditor,
   structured instance map and low-level action corrector for irreversible state
   changes.  CoPE should contrast bounded commitment edits with continuous
   multi-level replanning, not imply that existing systems lack interruption
   recovery.

6. [Reflective Planning (CoRL 2025)](https://proceedings.mlr.press/v305/feng25b.html)
   uses predicted future states and reflection to refine long-horizon robotic
   manipulation decisions.  It is less direct on persistent state transactions
   but blocks broad claims around first reflective long-horizon correction.

## Claim language that is currently unsafe

- "first robot method to repair instead of replan";
- "first symbolic constraint-guided failure recovery";
- "first persistent task-state approach" without a full claim-level search;
- "typed patches improve recovery" before beating the equal-information generic
  JSON-path transaction;
- "long-horizon generalization" from one task identity and two orientations;
- "learned embodied recovery" while using a privileged oracle skill controller.

## Claim language that the decisive experiment could support

If and only if the frozen gate passes, a bounded statement is plausible:

> In a controlled sequential-interruption setting, generating authorized typed
> commitment transactions is more reliable and local than generating equally
> informed generic JSON-path transactions, while preserving immutable completed
> progress and preventing stale commitment execution.

This still needs a fresh multi-task/real-robot replication for an ICRA-level
general robotics claim.  If CoPE ties or loses to generic JSON patch, reframe it
as a transaction/assurance framework that makes recovery state explicit and
verifiable; do not claim a learned representation advantage.

## Reviewer-facing missing work

- full-text comparison table against InstructFlow, plan-analysis repair,
  REFLECT, PLanAR and RePlan-Bot on state representation, repair unit,
  persistence, authorization, atomicity, history, idempotence and embodiment;
- at least one fresh task identity with a physically feasible four-object
  sequential interruption design;
- ablation separating typed operation vocabulary from validator/receipt/hash
  enforcement;
- explicit accounting that the low-level controller is privileged and shared;
- failure taxonomy showing whether any advantage comes from semantic locality,
  schema verbosity, parser compliance or true stale-state prevention.
