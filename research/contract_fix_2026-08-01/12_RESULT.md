# Shared semantic gate implementation result

Date: 2026-08-01 (Asia/Shanghai)

Implementation commit: `7395a58dd398a47ac86991b4c176956bb87e2149`

Validation/generalization commit: `f2013836900dfd836dd63bbba3437c19acd1667e`

Clean-readiness parent: `d5b5ea1f0956b2b20237325039cc8028efeccf9a`

## Decision

**The frozen semantic contract gate is fixed; the two-state oracle pilot remains
NO-GO because external and integration readiness gates are still missing.**

The unchanged preregistered 123-case audit moved from 62 expectation failures to
zero:

| Surface | Before | After |
|---|---:|---:|
| Replacement full-state-v2 | 32 malformed accepted | 0 |
| Cancellation full-state-v2 | 23 malformed accepted | 0 |
| Main full-state-v1 parser | 7 malformed accepted | 0 |
| Total expected decisions | 61/123 correct | **123/123 correct** |

All five valid/diagnostic controls remained accepted, and both canonical
diagnostic-prompt isolation controls remained unchanged. No expectation or case
in the frozen program was edited.

## What changed

- Added a shared, event-bound validator for canonical commitments, entities,
  progress, plan, restoration requests, and evidence versions.
- Replacement now rejects an already-completed pending original goal and
  duplicate current-goal atoms.
- Cancellation now applies the same persistent-section checks as replacement.
- The transitional main full-state-v1 parser pins its schema, requires nonempty
  commitments/plan and source/priority/lineage, derives the controller prompt
  deterministically from structured constraints and plan, and rejects a
  mismatching provider prompt.

The implementation contains no audit case IDs and no malicious-word blacklist.
It validates event-grounded structures. Exact closure is fail-closed for this
schema version; optional executable metadata requires an explicit schema change.

## Regression and overfitting checks

- Frozen audit: 123/123 expectation matches.
- Focused integration tests: 36 passed before the added generalization cases.
- Post-hoc generalization suite: 34 passed, including different state versions,
  `milk_1` replacement, the other original sibling as completed, reordered
  commitments/entities, extra non-executable top-level diagnostics, and
  priority/order-invariant main-v1 compilation.
- CoPE atomicity replay: 67 passed, including 64 manual counterexamples and the
  test executing 10,000 seeded operation sequences.
- Final full repository regression: **310 passed in 45.97 s**.

These checks reduce, but do not eliminate, the risk that exact canonical closure
is too restrictive for future provider schemas. That is a schema-evolution
question, not a reason to silently accept inconsistent task state now.

## Why the pilot is still blocked

The default validation command fails before readiness because
`data/disturbance_atlas_v1.jsonl` does not exist. A true-clean-worktree readiness
run using the explicit test fixture correctly reports `ready=false`,
`rollout_authorized=false`, and `formal_evidence_eligible=false`. Remaining
blockers are:

1. no formal semantic-replacement atlas and real atlas commit;
2. no configured non-fake high-level provider;
3. no configured non-fake simulator-predicate revalidation adapter;
4. no ready rollout backend under the missing provider, and no formal semantic
   replacement/cancellation runner in the main comparison path;
5. external dependency provenance is not formal (`fixture-atlas`);
6. `statsmodels` is absent from the analysis environment;
7. main full-state-v1 hardening is transitional; native FSR-PC and materialized
   post-CoPE state still do not share full-state-v2 in the formal runner;
8. the main config still points to the spatial checkpoint/event family, not the
   semantic task-1 pilot manifest.

The readiness output also exposed an instrumentation pitfall: piping stdout
directly into a new worktree artifact makes the cleanliness check see that
artifact as untracked. The authoritative run therefore captured stdout in
`/tmp` and copied it only after readiness completed; it reports
`git_worktree_clean=true` and retains the real blockers above.

## Scientific interpretation

This change removes a known fairness confound: malformed full rewrites and
provider prompt injection no longer receive weaker acceptance in the audited
surfaces. It still does **not** demonstrate that CoPE outperforms FSR-PC, nor
does it provide learned-provider or embodied evidence.

States 25–49 remain untouched. The next implementation slice is the formal
semantic runner/materialization boundary plus real validator/provider adapters;
only after their readiness checks pass may state 25 and state 26 be consumed.
