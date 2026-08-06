# X16 decomposed completeness-validator preregistration

Frozen date: 2026-08-03 (Asia/Shanghai)

## Question

X15 showed that an oracle-free typed interpreter blocks commission errors but
materializes every omission probe. The current common validator catches those
by comparing the entire candidate with a fully known correct state. X16 asks
whether explicit event-contract predicates can replace that oracle equality on
the frozen suite.

## Frozen validator constraint

The new validator module may inspect only candidate state, pre-state, and event.
It may not import, call, or contain the symbols `expected_patch`,
`derive_post_state`, or `validate_and_compile`, and may not hash/serialize the
entire candidate and compare it with an expected full state. A static source
audit is mandatory.

## Frozen predicate groups

The eight groups in `01_PREDICATE_MANIFEST.csv` are evaluated independently and
return named violations. Acceptance requires zero violations.

Checks may compare explicitly scoped pre/post fields when the contract says a
field must be preserved. This is not counted as whole-state oracle equality;
the exact field and reason must be visible in a named group.

## Frozen candidate population

Replay the exact 48 clean and 88 faulty four-arm proposals from X15 through the
same native parsers/materializers. The expected population from the committed
X15 raw results is:

- 48 clean materialized candidates;
- 39 faulty materialized noncanonical candidates;
- 49 faulty proposals rejected before candidate materialization.

Compare the decomposed validator with the existing exact oracle validator only
on materialized candidates. The exact validator is a control, not an allowed
dependency of the new module.

## Outcomes and gates

1. **Clean specificity:** decomposed validator accepts 48/48 clean candidates.
2. **Frozen-suite sufficiency:** decomposed validator rejects 39/39 materialized
   faulty candidates, matching the exact validator on accept/reject.
3. **Full-pipeline safety:** native rejection plus decomposed validation rejects
   88/88 faulty cells, with zero caller mutation or crash.
4. **Audit:** forbidden-symbol source audit and independent CSV-only audit pass.
5. **Ablation:** for each group, report fault count violated, unique-catch count,
   and number of faulty candidates that would pass if only that group were
   removed. No group is removed from the final validator based on this small
   suite.

If any bad candidate has zero decomposed violations, the sufficiency gate fails;
retain the run and diagnose rather than silently changing results. A corrected
validator requires a new versioned run and an explicit pre-result rationale.

## Claim boundary

Passing supports only that the named predicates are sufficient on this frozen,
hand-designed candidate set. It is not formal completeness, adversarial
security, learned-generation robustness, or robot success. Correlated checks
and zero unique catches do not prove a predicate unnecessary.

Use no provider, credential, LLM, GPU, simulator, robot, or LIBERO state 27--49.

