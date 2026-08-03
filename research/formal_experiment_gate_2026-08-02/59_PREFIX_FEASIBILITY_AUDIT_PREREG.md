# Shared-prefix feasibility audit preregistration

Status: designed, not executed.

## Purpose

Diagnose the state-33 `grasp_not_acquired` common-substrate failure without
touching formal states 33--49 or issuing method/provider calls.

## Frozen proposed audit

- LIBERO-10 task 1, development states 5--24 exactly once each;
- same seed=`state_id`, oracle controller configuration, warmup, cream-cheese
  placement and five-step stability check as the formal runner;
- CPU only; zero provider credentials and calls;
- no retry, controller change, state skip or replacement outcome execution;
- retain every success/failure, action-prefix hash, simulator-state hash,
  action count, failure class and initial-state hash;
- states 25--49 remain unindexed;
- primary output: prefix success rate and failure-class distribution;
- secondary diagnostic: compare initial/prefix provenance of successful and
  failed states without tuning on a held-out formal state.

## Decision rule

If any development state fails, the current shared controller is not suitable
as a guaranteed formal event constructor. Controller repair must be developed
and frozen using only states 0--24, followed by a separate development
validation split. If all pass, state 33 remains a documented out-of-support
configuration and a future formal benchmark must predefine how common-prefix
failures enter the denominator.

This audit must be implemented, tested and committed before execution. It does
not authorize another formal-state attempt.
