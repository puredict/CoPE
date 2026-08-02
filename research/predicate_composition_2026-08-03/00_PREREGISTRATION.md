# X17 decomposed-predicate composition stress preregistration

Frozen date: 2026-08-03 (Asia/Shanghai)

## Motivation

X16 matched the exact validator on 39 materialized single-fault candidates, but
many faults violated correlated predicate groups. This experiment constructs
isolated group-level mutations and their compositions to test attribution and
one-at-a-time necessity more sharply.

## Frozen construction

Use the canonical `replace_pending_target` post-state for seven independent
mutations targeting:

- version/evidence;
- stable identity/lifecycle;
- goal consistency;
- progress preservation;
- action continuity;
- restoration/entity;
- unaffected scope.

Enumerate every size-1, size-2, and size-3 combination: `7 + 21 + 35 = 63`
candidates. Add one authorization/no-op singleton using the
`wrong_source_revoke` case, for 64 faulty candidates total.

Each mutation is frozen in `01_MUTATION_MANIFEST.csv`. Mutation application
order is the manifest order. Candidates are direct deterministic state
mutations, not provider or representation outputs.

## Frozen predictions and gates

1. The 12 canonical case states pass with zero violations.
2. Every faulty candidate differs from its canonical state.
3. Decomposed validator rejects 64/64 and exact validator rejects 64/64.
4. For every candidate, the observed violated-group set equals exactly the
   groups named by its component mutations. Any extra or missing group fails
   the attribution gate.
5. The eight singleton candidates each violate exactly one distinct group.
   Removing that group alone therefore makes its singleton pass; every group
   must have one ablation fail-open.
6. No crash or caller-state mutation is allowed.

This is a white-box stress test and deliberately favors isolation. Passing does
not prove soundness for arbitrary interacting edits, nor does it measure
learned generation, security, or robot recovery.

Use no provider, credential, LLM, GPU, simulator, robot, or LIBERO state 27--49.

