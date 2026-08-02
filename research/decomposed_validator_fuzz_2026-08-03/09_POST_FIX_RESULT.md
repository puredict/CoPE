# X18 post-fix observed-seed and holdout result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS for the narrowly preregistered structural repair; formal learned and
embodied gates remain NO-GO.**

The repair added only the frozen constraints: canonical commitment/entity ID
order and exact record field sets. Three minimal regressions cover the original
false-accept classes. The decomposed validator still contains no call to the
oracle post-state constructor or exact validator.

## Results

| Run | Clean accepted | Assigned | Actually changed | Exact/decomposed parity | Caller unchanged | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| observed seed 20260803 | 12/12 | 3,000 | 2,997 | 3,000/3,000 | 3,000/3,000 | regression PASS |
| unseen holdout 20260804 | 12/12 | 3,000 | 2,992 | 3,000/3,000 | 3,000/3,000 | repair holdout PASS |

For the holdout's 2,992 changed candidates, exact/decomposed decision parity
was 2,992/2,992. There were zero exact-reject/decomposed-accept and zero
exact-accept/decomposed-reject cells. The eight unchanged assignments were
multi-mutation cancellations, retained in the raw table.

The original experiment program prints `decision=FAIL` whenever even one
assigned mutation sequence cancels itself. That raw status is preserved. The
post-fix holdout preregistration, frozen before implementation, explicitly
changed the validator-decision denominator to final-byte-changed candidates;
under that rule the repair passes. This is not a retroactive reinterpretation
of v1: v1 remains FAIL because it contained 24 real decision mismatches.

## Regression

- focused decomposed/predicate suites: 14 passed;
- complete repository regression after repair: 445 passed in 47.25 seconds.

## Claim boundary

This supports only extensional accept/reject agreement under two seeded
synthetic structural/field mutation distributions. It does not prove semantic
completeness or safety and supplies no evidence that CoPE is easier for a
learned model than compact transactions or full-state regeneration. No GPU,
provider, robot simulator, or reserved LIBERO state was used.
