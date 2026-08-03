# Sequential formal analysis preregistration

Date: 2026-08-04

Manifest SHA-256:
`1fe0b231bb17e9ed0711c76ee440928faccf84696043ac0a84ddd9645bf6b7ec`.

## Input integrity

The event-result table must contain exactly one row for every planned
`sequence_id x arm x event_index` cell: 40 x 4 x 2 = 320 rows.  No duplicate,
missing, or extra cell is accepted.  `substrate_eligible` must be identical
across all eight rows of a sequence.  An ineligible shared prefix has no
provider call in any arm and is reported only in the substrate denominator.
Every eligible event-1 cell must record one provider attempt and zero retries.
Event 2 must also be attempted unless event 1 failed; in that case it must have
no call and the exact failure class `dependency_skip_after_event1_failure`.
For every eligible sequence, all eight rows must share nonempty physical-prefix
action and simulator hashes.  All attempted calls at the same event index must
also share one nonempty common-input hash across arms.  Any divergence aborts
analysis rather than becoming a method outcome.

## Frozen sequence endpoint

For an eligible sequence-arm pair, success requires:

1. both calls parse and validate semantically;
2. both transitions have revision/hash continuity and valid intermediate
   invariants;
3. completed physical progress is preserved after both transitions;
4. no superseded commitment is executed;
5. the event-2 final intent (HALT or final placement) is satisfied;
6. action and call budgets are respected on both events.

Timeout, provider outage, parse failure, semantic rejection, dependency skip,
invariant failure,
stale execution, incorrect final intent, retry, or budget violation is a
sequence failure.  There is no repair or imputation.

## Comparisons

The primary paired comparison is CoPE versus neutral patch over eligible
sequences, using a two-sided exact McNemar/binomial test.  Report:

- success rates;
- paired risk difference in percentage points;
- discordant counts (CoPE-only wins and neutral-only wins);
- exact conditional discordant-win probability interval (Clopper-Pearson);
- exact matched odds-ratio interval derived from that probability interval.

Secondary CoPE-versus-FSR-PC and CoPE-versus-full-replan exact McNemar tests
are adjusted together by Holm's method.  No subgroup test changes the primary
decision.  Forward/reverse prefix and cancel/double-replace tables are
descriptive only.

Before learned outcomes, the necessary decisive-experiment gate is frozen as
all of the following:

1. CoPE versus neutral patch has two-sided exact McNemar `p < 0.05` and paired
   success-rate difference at least `+0.15`;
2. CoPE has no greater count of stale-execution sequences and no greater count
   of invariant-violation sequences, where invariant violation includes either
   intermediate invariant failure or revision/hash discontinuity;
3. among sequence pairs where both methods produce parser-valid and
   semantic-valid proposals on both events, CoPE has at least 20% median paired
   reduction in total proposal bytes and a two-sided exact sign-test `p < 0.05`
   after discarding byte ties.

This gate is necessary but not sufficient for submission because the locked
study contains one task identity.  A success tie/loss, safety excess, or missing
locality gate triggers the assurance-framework reframe and is not rescued by
secondary comparisons.  Prompt tokens and latency are reported but cannot
satisfy the locality gate because arm contracts differ in length and provider
latency is noisy.
