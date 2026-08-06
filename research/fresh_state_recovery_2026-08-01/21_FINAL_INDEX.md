# Fresh-state recovery decision package

Date: 2026-08-01 (Asia/Shanghai)

## Decisions

1. **Retain local staging only as an oracle recovery-efficiency ablation.** On
   preregistered, previously uninspected states 15–24, exact return and local
   staging both achieved 10/10 physical updated-goal success. Local staging was
   faster in 10/10 pairs, saving 36.2 actions on average (median 35.5).
2. **Do not claim improved safety.** The corrected force-impulse proxy favored
   local in 10/10 pairs, but peak force favored local in only 4/10, the hazard
   proxies were sparse, and the contact-force estimate is not calibrated safety
   instrumentation.
3. **Keep the formal CoPE–FSR-PC experiment at NO-GO.** The main runner still
   lacks a real provider and validator, sends the two methods through unequal
   compilation paths, and implements spatial displacement rather than the
   semantic-replacement kill test.
4. **The existing full-state canary validator is insufficient.** A deterministic
   16-case adversarial audit found seven accepted malformed outputs involving
   progress, plan, entities, or evidence versioning.
5. **Preserve states 25–49.** Do not use them for controller tuning. They are the
   untouched reserve for a locked validation after the semantic baseline gates
   pass.

## What happened in the two fresh runs

The first frozen run on states 5–14 used the inherited 40-step Cartesian phase
limit. State 5 failed before the interruption in all three arms, so the assigned
comparison was **inconclusive**, not a rejection of local staging. Conditional
on the nine valid paired events, both recovery arms succeeded 9/9 and local was
faster 9/9.

A correct-target diagnostic on the already consumed state 5 localized the
failure: descent stopped after 40 moves at 8.45 mm error and did not retain the
object. Raising the common per-phase cap to 60 allowed convergence in 45 moves
and reached the milestone. This single controller change was then frozen in a
second preregistration before inspecting states 15–24. All 30 assigned arms ran
with that same budget and completed.

## Evidence map

- `00_PREREGISTRATION.md`: first frozen protocol.
- `03_RESULT_v2_PROTOCOL_CORRECTED.md`: authoritative first-run interpretation.
- `05_FSR_PC_READINESS_AUDIT.md`: main end-to-end blockers.
- `09_STATE5_AND_REPORT_CORRECTION_AUDIT.md`: invalid diagnostic disclosure,
  corrected target, and report correction.
- `12_MAX60_PREREGISTRATION.md`: second protocol, committed before raw results.
- `14_FULL_STATE_VALIDATOR_COVERAGE.csv`: 16 adversarial/control decisions.
- `15_FULL_STATE_VALIDATOR_GAPS.md`: validator NO-GO analysis.
- `16_MAX60_ASSIGNED_EPISODES.csv`: all 30 second-run assigned cells.
- `17_MAX60_RESULT.md`: frozen-rule result.
- `18_MAX60_INTEGRITY_AND_STATISTICS.md`: anti-fabrication and uncertainty audit.
- `19_FULL_PYTEST.txt`: 297 passing tests.
- `20_VALIDATOR_AUDIT_REPLAY.txt`: deterministic reproduction of the seven gaps.
- `max60_raw_v1_preregistered/`: 30 raw CSVs and 30 stdout/stderr logs.

## Next executable gate

Before spending any reserve state, require all of the following:

- one canonical full-state-v2 representation for native FSR-PC output and the
  materialized post-CoPE state;
- a neutral validator that rejects the seven observed corruption classes;
- a single deterministic compiler used by both arms, ignoring provider-supplied
  controller prose;
- a non-fake provider implementing `regenerate` and `patch` from byte-identical
  recovery inputs and equal inference budgets;
- a non-fake simulator-predicate revalidation adapter;
- a semantic replacement/cancellation manifest and runner with matching
  pre-event action/state hashes.

Then run CPU contract and corruption tests, followed by a two-state oracle
pilot. Only a clean oracle pilot authorizes a learned-provider pilot. The first
learned comparison should emphasize generation validity, stale references,
atomicity, progress preservation, latency, and token cost; it should not expect
an artificial physical-success gap after both methods compile to equivalent
accepted task states.
