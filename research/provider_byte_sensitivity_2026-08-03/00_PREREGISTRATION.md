# X20 contract-overhead sensitivity preregistration

Frozen: 2026-08-03 before running the sensitivity program; X19 results are
known and are the fixed input.

## Reviewer challenge

X19's compact-TX contract is 639 UTF-8 bytes longer than CoPE's. The observed
per-call result may therefore depend on prompt encoding rather than proposal
factorization.

## Frozen scenarios

Using all 12 X19 cases without exclusions, compare corpus-total bytes under:

1. actual contract sent on every call;
2. hypothetical provider-side schema cache, with the exact arm contract wire
   overhead paid once and an empty-contract base request on the other calls;
3. proposal bytes only.

Also report the number of individual cases in which each arm is tied for the
smallest proposal. PASS for the narrow corpus-total robustness statement
requires CoPE to have the smallest total in all three scenarios. PASS does not
permit a per-case dominance claim and does not measure tokens or correctness.
