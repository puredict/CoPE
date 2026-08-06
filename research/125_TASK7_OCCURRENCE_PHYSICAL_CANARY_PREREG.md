# Task-7 occurrence-restoration physical canary preregistration

Date: 2026-08-04  
Status: frozen before the new physical episode

## Scope

- LIBERO-10 task 7, already exposed development state 0 only;
- two independently reset modes in fixed order: `cancel`, then `restore`;
- no task-7 state 1--49 access;
- no provider call or learned policy;
- CPU-only oracle skill controller with the frozen bounded-regrasp
  configuration hash
  `56171aef20a9f60e335259ff10abe7c211f6594a98b52b09864effcc7b1d988a`.

The prior task-7 access only inventoried state 0 and found the absent fourth
object. This canary tests the redesigned three-object sequence; it does not
retroactively repair or reuse an outcome.

## Procedure

1. Reset state 0 and place `alphabet_soup_1` in
   `basket_1_contain_region`.
2. Require five stable checks with alphabet soup in the basket and both
   `cream_cheese_1` and `tomato_sauce_1` outside.
3. Apply the two occurrence-addressed oracle events entirely in memory:
   cream-cheese occurrence 1 -> tomato-sauce occurrence 1, then either cancel
   or tomato-sauce occurrence 1 -> cream-cheese occurrence 2.
4. Prove the semantic phase emits no action and preserves the simulator hash.
5. For `cancel`, execute nothing and require soup true, cream false, tomato
   false. For `restore`, execute the compiled cream-cheese placement and
   require soup true, cream true, tomato false for five stable checks.

## Gate and stop rule

PASS requires both independent modes to meet every prefix, semantic no-action,
simulator-preservation, terminal predicate, action-budget, and controller-skill
criterion. Any failure stops task 7 without tuning or retry. A PASS authorizes
only a separate preregistration for states 1--9; it does not authorize those
states, formal states 10--29, or provider calls.
