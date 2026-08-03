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
Every eligible cell must record one provider attempt and zero retries.

## Frozen sequence endpoint

For an eligible sequence-arm pair, success requires:

1. both calls parse and validate semantically;
2. both transitions have revision/hash continuity and valid intermediate
   invariants;
3. completed physical progress is preserved after both transitions;
4. no superseded commitment is executed;
5. the event-2 final intent (HALT or final placement) is satisfied;
6. action and call budgets are respected on both events.

Timeout, provider outage, parse failure, semantic rejection, invariant failure,
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

Submission GO requires a statistically and practically meaningful CoPE gain
over neutral patch plus no excess stale execution/invariant violation and at
least one efficiency/locality advantage.  A tie or loss triggers the previously
specified assurance-framework reframe; it is not rescued by secondary tests.
