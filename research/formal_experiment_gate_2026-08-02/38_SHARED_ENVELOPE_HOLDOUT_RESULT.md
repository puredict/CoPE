# Shared-envelope holdout result and compact-semantics audit

Date: 2026-08-03 (Asia/Shanghai)

## Frozen run

The preregistered 36-case, four-arm holdout completed all 144 OpenRouter calls.
All 144 calls were provider-OK and schema-valid. The final per-arm CSV contains
144/144 `fairness_pass=true`, comprising 36/36 byte-identical common-input and
normalized-request quadruplets. There was no retry, repair, fallback, oracle
substitution, transaction-metadata generation, GPU/simulator use, or reserved
state access.

Raw run commit: `111487204017b03a0fea82ea258324d5aab55c1a`.

The raw runner status contains `fair_quadruplets=6`. This is a reporting bug:
the value was hard-coded for the earlier six-case development set. Direct
recomputation from `04_PER_ARM_RESULTS.csv` gives 36. The source was corrected
without modifying the immutable run output.

## Original executor score

| Arm | Correct / 36 |
|---|---:|
| CoPE semantic typed delta | 36 |
| Neutral typed delta | 34 |
| Compact natural-path transaction | 29 |
| Full semantic state | 32 |

Original paired results were CoPE versus compact 7--0 (raw `p=0.015625`,
Holm `p=0.03125`) and CoPE versus neutral 2--0 (raw/Holm `p=0.5`). The runner
therefore emitted `PASS` under the frozen threshold.

## Fairness defect discovered after completion

The compact prompt allowed whole-record paths such as `/actions/<id>` and
named the operations `add`, `replace`, and `remove`, but the executor rejected
`replace` at an existing whole-record path. Three compact outputs used that
reasonable object-member JSON Patch operation and were semantically identical
to the oracle. Treating them as errors unfairly weakened the compact baseline.

The executor and contract were corrected to state and implement object-member
semantics:

- `add` creates an absent member or replaces an existing member;
- `replace` requires and replaces an existing member;
- `remove` requires and removes an existing member;
- a whole-record value must be complete and its `id` must match the path.

Correction commit: `47da0df4409476c66c257e705a41b2573af0def3`.
Fourteen shared-envelope and holdout tests pass.

## Immutable-response sensitivity rescore

The 144 raw responses were re-evaluated under the corrected executor; no model
was called and no response was changed.

| Arm | Correct / 36 | Change |
|---|---:|---:|
| CoPE semantic typed delta | 36 | 0 |
| Neutral typed delta | 34 | 0 |
| Compact natural-path transaction | 32 | +3 |
| Full semantic state | 32 | 0 |

The corrected CoPE-versus-compact discordance is 4--0, two-sided exact
`p=0.125`; with the two frozen contrasts, Holm-adjusted `p=0.25`. CoPE versus
neutral remains 2--0, Holm-adjusted `p=0.5`. The corrected decision is **FAIL**.

Remaining compact failures are: H09 wrong progress identifier/content, H17 an
incomplete whole-record replacement, H30 `replace` on an absent field, and H31
`replace` on an absent fact. These remain genuine first-pass semantic errors.

## Scientific decision

The original `PASS` is not valid submission evidence. The run still shows a
strong ceiling for the shared trusted commit envelope and suggests that
semantic typed operations can reduce representation errors, but it does not
separate CoPE from an equally sparse neutral typed interface and no longer
separates it significantly from the corrected compact interface.

The next admissible test is a newly frozen confirmation set using the corrected
compact semantics. No embodied or reserved-state experiment should be promoted
as the key test until that confirmation gate passes.
