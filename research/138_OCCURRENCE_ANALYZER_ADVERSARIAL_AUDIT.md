# Occurrence formal analyzer adversarial audit

Date: 2026-08-04

## Decision

**PASS after evidence-anchoring amendment.** The locked analyzer now rejects
corrupt result tables before computing efficacy or locality.

## Gap found

The previous analyzer required each case's five arms to share one nonempty
input hash, but did not prove that the shared hash was the manifest-derived
recovery input. A coherently drifted five-arm group could therefore pass the
common-input check. It also trusted result metadata and success booleans
without requiring the corresponding proposal, candidate, and response hashes.

This was an artifact-integrity gap, not an observed experiment outcome. No
live learned formal call has occurred.

## Amendment

For every manifest case, the analyzer now deterministically rebuilds the
occurrence pre-state, event, and common recovery input, then requires every arm
to carry that exact input SHA-256. It additionally requires:

- exact case/sequence, triple-index, and recurrence-depth metadata;
- exactly 200 unique expected cells;
- zero retries and one provider call per cell;
- canonical boolean encodings and coherent parser/semantic/invariant flags;
- positive proposal bytes plus a proposal SHA-256 for parsed outputs;
- a candidate SHA-256 for semantic outputs;
- an empty failure class plus a response SHA-256 for complete successes;
- a nonempty failure classification for parser or semantic failures.

## Adversarial tests

The test suite independently rejects:

1. a missing result cell;
2. a manifest-inconsistent input hash;
3. a nonzero retry count;
4. sequence metadata drift;
5. missing proposal hash evidence;
6. missing candidate hash evidence;
7. missing response hash evidence on success;
8. a noncanonical boolean;
9. impossible semantic/invariant flag combinations.

Infrastructure failure still yields
`INVALID_INFRASTRUCTURE_FAILURE`, while a valid synthetic dual-primary result
retains the preregistered decision path.

## Verification

- focused analyzer tests: 11 passed;
- full repository suite: 613 passed;
- provider calls: 0;
- simulator states indexed: 0.

## Consequence

The 200-call formal run can be analyzed only if its result evidence is tied to
the frozen manifest-derived inputs. This closes a false-positive path without
changing hypotheses, thresholds, arm contracts, or planned outcomes.
