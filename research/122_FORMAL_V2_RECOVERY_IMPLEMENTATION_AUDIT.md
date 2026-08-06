# Formal v2 recovery implementation audit

Date: 2026-08-04  
Implementation commit: `17b6a0a669b0dafc2f4172984086a2f16f9b273c`

## Decision

**PASS for crash-recovery implementation; formal execution remains blocked at
the credential/smoke gate.** No formal provider outcome was produced.

## Evidence

- Full regression: **593/593** tests passed.
- A received provider response was rematerialized twice with the fixture
  provider call counter remaining exactly **1**.
- A durable intent without a response failed closed as
  `ambiguous_interrupted_call_no_retry`, with the fixture provider call counter
  remaining exactly **0** after resume.
- Duplicate keys, orphan responses, metadata drift, and torn JSONL lines were
  rejected.
- Results with provider calls require both a durable intent and response,
  except the explicitly ambiguous no-response terminal record.
- The runner writes intent, response, and result journals with `fsync`, pins
  run metadata, skips completed cells, rematerializes response-only cells, and
  atomically publishes the final CSV from the result journal.
- The analyzer now gives provider timeout, HTTP error, transport outage, or
  ambiguous interrupted call the run-level status
  `INVALID_INFRASTRUCTURE_FAILURE` instead of treating it as method evidence.
- A clean-commit invocation without `OPENROUTER_API_KEY` again exited with code
  **3**, with **0** provider calls and **0** simulator states indexed.

## Remaining limit

The local journal provides at-most-once draws, not distributed exactly-once
delivery. If the provider processes a request but the client loses the
response, the call remains epistemically ambiguous and invalidates the run.
No retry is permitted.

## Small fairness correction still required

The v2 runner should check receipt hash continuity for neutral and governed
transactions as well as CoPE. Both controls already emit before/after hashes;
omitting their check makes the recorded field asymmetric even though shared
semantic validation still enforces state continuity. This correction is
frozen before any outcome and must pass regression before the runner is marked
launch-ready again.
