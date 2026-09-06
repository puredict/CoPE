# X18 structure-agnostic state-mutation falsifier preregistration

Frozen date: 2026-08-03 (Asia/Shanghai)

## Motivation

X17's mutations were designed around known predicate groups. X18 instead walks
the complete JSON tree of each canonical post-state and applies a fixed grammar
without reading validator violations or predicate names.

## Frozen corpus and mutation grammar

Use all 12 frozen canonical N-track post-states. At every applicable path,
generate one candidate for each operator in `01_OPERATOR_MANIFEST.csv`:

- delete each mapping field;
- add one unknown field to each mapping;
- drop each list item;
- duplicate each list item;
- append a scalar sentinel to every list;
- reverse each non-palindromic list of length at least two;
- mutate each scalar deterministically by type.

Deduplicate candidates only within a case by full candidate SHA-256, retaining
the first traversal assignment. Traversal is depth-first and mapping/list order
is the canonical Python insertion/index order. No randomness or result-dependent
operator change is allowed.

## Frozen comparison and classification

Every retained candidate must differ from its canonical state and be rejected
by the existing exact validator. Run `decomposed_violations` separately and
record any exception.

An exact-reject/decomposed-accept divergence is classified as
`order_only_divergence` only when all conditions hold:

1. operator is `reverse_list`;
2. path is exactly `/commitments`, `/entities`, or `/progress_ledger`;
3. the list has the same element multiset and differs only in order.

This allowlist is frozen before results. Such a divergence is not called fully
benign: semantic conjunction/record order may be irrelevant, but canonical
hashes and deterministic receipts still differ. Every other decomposed accept
is a `dangerous_blind_spot`.

## Gates

1. 12/12 clean controls pass both validators.
2. Every retained mutation changes the canonical state and exact validator
   rejects it.
3. Zero validator exceptions/crashes and zero caller-state mutations.
4. Zero dangerous blind spots.
5. Report, do not suppress, every order-only divergence by case/path/hash.
6. Independent CSV-only audit recomputes counts and classification.

If dangerous blind spots occur, the gate fails. Do not modify the validator
inside this preregistered run; preserve results and create a separately versioned
repair only after diagnosis.

## Claim boundary

Passing means only that this deterministic one-edit grammar found no dangerous
blind spot on 12 small states. It is not exhaustive over values, multi-edit
interactions, adaptive adversaries, learned outputs, or robot behavior.

Use no provider, credential, LLM, GPU, simulator, robot, or LIBERO state 27--49.

