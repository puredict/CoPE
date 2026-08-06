# X16 overlap and leakage audit

## Verdict

**PASS with a bounded claim.** None of the 36 templates is a context variant of
another X16 template or a transition-equivalent copy of an X14 template. The
corpus is suitable for template-level paired inference, conditional on its
constructed-test-set limitation.

## Independence checks

Every template has a unique normalized logic signature covering the decision
premise, dependency graph, semantic operator sequence, continuity/progress
effect, concurrency relation, and disposition. The two templates within each
required family deliberately test different logic. Examples include AND-cascade
versus OR-support cancellation, single versus non-LIFO nested release, direct
versus transitive dependency replacement, exact replay versus event-ID
collision, low authority versus wrong owner scope, and commuting versus
noncommuting concurrent events.

The irrelevant-scaling cases are not X14-style repetitions. One edits a single
deadline inside a heterogeneous mixed-status dependency graph with 25
commitments and eight milestones; the other performs an aggregate capacity
proof across 20 shared-resource dependents and correctly yields NO_OP. Neither
is counted as more than one template.

The closest-X14 comparison and case-specific reason are recorded for every row
in `06_X16_OVERLAP_LEAKAGE_AUDIT.csv`. Case/object renaming, identifier changes,
version changes, and appended context were not used as admission evidence.

## Input leakage checks

Provider-visible common inputs omit:

- oracle post-states and hashes;
- oracle disposition and reason code;
- CoPE operations, compact writes, or FSR-PC answers;
- expected execution directive;
- primary-family and secondary-tag labels;
- X14 closest-template and difference fields;
- scoring or qualification outcomes.

Task policies are intentionally visible because they define the semantics to be
solved; this is not answer leakage and is identical across arms. The common
reason-code vocabulary is also visible to all arms. A recursive forbidden-key
scan passed all 36 inputs, and normalized request hashes matched for all 108
arm cells.

## Residual risks

Templates were deliberately authored after X14, so X16 is a preregistered
constructed replication, not an untouched natural holdout. Some cases combine
families, so family-wise descriptive rates are not causally isolated factorial
effects. Unique logic signatures establish non-duplication under the frozen
feature definition; they cannot prove statistical sampling independence from a
real deployment distribution. These limits must accompany any reported p-value.
