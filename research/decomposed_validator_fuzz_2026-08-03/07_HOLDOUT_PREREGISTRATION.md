# X18 post-fix holdout preregistration

Frozen: 2026-08-03 before implementing the validator repair.

## Repair scope

The only authorized validator changes are:

- enforce canonical commitment ID order (pre-state order, then event-created
  record if applicable);
- enforce canonical entity ID order (pre-state order, then event-created
  entity if applicable);
- require every existing commitment/entity record to retain its exact field
  set, and every event-created record to have its already specified exact
  field set.

The decomposed validator may not call `derive_post_state`,
`validate_and_compile`, an expected-patch helper, or compare a whole-candidate
hash to an oracle state.

## Verification

1. Add minimal unit regressions for the three observed false-accept classes.
2. Rerun seed `20260803` only as a labelled observed-seed regression.
3. Run an unseen holdout using seed `20260804`, 250 candidates per case and the
   unchanged 12-case manifest/mutator distribution.
4. Because the original mutator permits cancelling multiple edits, the holdout
   decision denominator is all candidates whose final bytes differ from the
   clean control. Unchanged assignments remain reported but are not validator
   counterexamples.

PASS requires 12/12 clean acceptance, exact/decomposed parity for every changed
holdout candidate, no exact-reject/decomposed-accept, no
exact-accept/decomposed-reject, and no caller-state mutation. Any holdout
mismatch is retained and fails the repair.

A PASS repairs only the demonstrated structural differential under this
synthetic distribution. It does not establish learned or embodied performance,
semantic completeness, or a CoPE-specific advantage.
