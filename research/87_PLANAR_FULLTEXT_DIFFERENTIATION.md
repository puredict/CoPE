# PLanAR v4 full-text differentiation note

Date: 2026-08-04

Primary source: [PLanAR arXiv v4 HTML](https://arxiv.org/html/2602.01662v4).

## Direct overlap

PLanAR already provides an explicit planning-language state with object
predicates, action schemas, preconditions and effects.  It verifies expected
effects after every action, updates symbolic task state, detects failures and
recovers under human disturbance.  Its experiments include real robots,
multiple tasks, multiple VLMs and cross-embodiment transfer.  CoPE must not claim
first explicit symbolic task state, first verification-based recovery, or first
long-horizon state update after disturbance.

PLanAR also demonstrates the empirical standard reviewers can demand.  A
single-task LIBERO study with an oracle skill controller is not competitive as a
broad embodied-robotics validation, even if internally well controlled.

## Clear methodological contrast

PLanAR states that after a failed verification the task parser re-instantiates
an updated PDDL problem from the current world state and the symbolic planner
generates a revised action sequence.  This is a strong concrete example of the
full-replan family against which CoPE's bounded commitment transaction should be
contrasted.

Exact HTML full-text searches returned no match for `commitment`, `idempot`,
`transaction`, or `history`.  As with all keyword checks, absence of a token is
not proof that no equivalent idea appears under different terminology.  The
inspected formulation nevertheless does not expose stable interruption-targeted
commitment identities, event/base-version authorization, atomic receipts,
duplicate-event rejection, or preserved inactive commitment history.

## Paper implication

The defensible comparison is:

- PLanAR/full replan: update the observed symbolic world, instantiate a new PDDL
  problem and generate a revised action sequence;
- CoPE: preserve an existing persistent commitment ledger and apply one
  authorized versioned transaction to the interrupted commitment;
- generic JSON patch: test whether the benefit is transaction locality itself
  or specifically CoPE's typed operation vocabulary and assurance machinery.

For ICRA positioning, a positive locked result should be followed by at least
one new task identity and preferably a real-robot or non-oracle-controller
replication.  Otherwise the paper should be framed as a transaction/assurance
method with controlled embodied evidence, not as a stronger general robot agent
than PLanAR.
