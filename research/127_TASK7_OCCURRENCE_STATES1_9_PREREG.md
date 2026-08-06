# Task-7 occurrence-restoration states 1--9 preregistration

Date: 2026-08-04  
Status: frozen before indexing task-7 state 1

## Fixed cells

- LIBERO-10 task 7, state IDs 1 through 9 in ascending order;
- within each state: `cancel`, then `restore`;
- exactly 18 independently reset episodes, one attempt per cell, no retry or
  state skip;
- CPU only, zero provider credentials/calls and no learned policy;
- frozen controller configuration hash
  `56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a`;
- task-7 states 10--49 remain locked.

## Per-cell criteria

Use exactly the state-0 procedure and criteria: stable alphabet-soup prefix,
semantic no-action, exact simulator preservation, occurrence-history validity,
mode-specific terminal predicates for five stable checks, successful terminal
skill when required, and total action count at most 700.

Write and `fsync` each cell before advancing. On the first failed cell, stop
without retry and do not index later states. Retain the failure and every prior
cell.

## Gate

PASS requires 18/18 successful cells, identical cancel/restore prefix action
and prefix simulator hashes within every state, no retries, and no forbidden
state/provider access. A PASS supports task-7 substrate external validity and
authorizes only a later learned-experiment design. It does not authorize task-7
formal states 10--29 or any provider call.
