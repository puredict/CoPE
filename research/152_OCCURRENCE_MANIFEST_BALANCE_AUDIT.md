# Occurrence manifest balance audit

Date: 2026-08-04

## Decision

**PASS for paired arm-order/depth balance; limited for lexical
generalization.** Every arm is compared within the same case, and arm position
is perfectly balanced overall and within recurrence depth. The ten object
triples are not perfectly role-balanced, which is unavoidable with seven
objects and ten triples and limits population claims.

## Exact balance

- 40 unique cases = ten triples x four recurrence depths;
- 40 unique seeds, consecutive from 20260850 through 20260889;
- five cyclic arm orders, each used eight times;
- every arm appears in every order position eight times overall;
- within each recurrence depth, every arm appears in every position exactly
  twice;
- every case contains all five arms with the same input and seed.

Object-role counts below are counts among the ten triples (each is repeated at
four depths):

| Object | done | recurring | intermediate |
|---|---:|---:|---:|
| alphabet_soup_1 | 2 | 1 | 1 |
| butter_1 | 2 | 2 | 1 |
| cream_cheese_1 | 2 | 2 | 1 |
| ketchup_1 | 1 | 2 | 2 |
| milk_1 | 1 | 1 | 2 |
| orange_juice_1 | 1 | 1 | 2 |
| tomato_sauce_1 | 1 | 1 | 1 |

## Interpretation

The paired comparison prevents an object name or recurrence depth from being
assigned to only one method. Perfect per-depth position balance also prevents
call order from being confounded with recurrence depth.

The benchmark nevertheless weights some objects twice in particular semantic
roles. A representation-by-token interaction could therefore be specific to
this vocabulary distribution. The formal result must be reported as a fixed
seven-object symbolic benchmark, not as object-balanced open-world evidence.

Expanding with more renamings after seeing outcomes is prohibited. A future
generalization set should preregister new vocabularies and semantic event
families, not merely rebalance these ten triples post hoc.
