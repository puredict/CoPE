# Result and claim boundary

Date: 2026-08-02 (Asia/Shanghai)

Preregistration/implementation commit: `e277c17`

Final reporting implementation commit before the authoritative preflight:
`e386a78`

## Decision

**The matched native-output harness is implemented and its offline fairness and
oracle controls pass, but the real-provider smoke is BLOCKED before any model
call because `OPENROUTER_API_KEY` is unavailable in both the local and remote
process environments. There is no CoPE-vs-FSR-PC native generation result yet.**

The authoritative credential-preflight directory is
`run_20260802_credential_preflight_v2/`. All 12 preregistered pairs (24 arm
cells) remain in the per-sample ledger as `configuration_blocked`;
`method_evaluable=0` for both arms. This is neither provider outage nor
method-invalid output: no HTTP request was made, no response exists, and the
response-hash cells are intentionally empty.

The earlier `run_20260802_credential_preflight/` directory is retained as an
audit trail but superseded for reporting because it emitted only a CSV header
instead of retaining the 24 assigned blocked cells. No model output was observed
between the two preflights, and the scientific stopping rule did not change.

## What passed

- Static fairness preflight: 12/12 pairs have identical `RecoveryInput`, common
  input-message bytes, and provider-visible request hashes after replacing only
  the arm-specific output contract with a sentinel.
- Oracle transport control: 12/12 pairs, 24/24 arm cells, pass the arm parser,
  common event-bound validator, and common compiler when canonical outputs are
  injected through the adapter's mocked transport. These are tests, not model
  samples.
- Required semantics include no-op, cancellation, replacement, override and
  release, release after world change, wrong-source and stale no-edit,
  idempotence, irrelevant change, and valid/invalid action continuity.
- Focused native tests: 20 passed.
- Final full repository regression: 361 passed in 46.90 seconds.
- Provider `controller_prompt` is outside both accepted schemas and is never
  executed.
- Provider calls: 0; robot/simulator/controller calls: 0; reserve states read:
  0; retries: 0; repairs: 0; secrets logged: 0.

## What cannot be claimed

There is no measured first-pass valid rate, semantic-correctness rate, token
count, latency comparison, or failure taxonomy for either method. Zeros in the
aggregate are bookkeeping counts with a zero method-evaluable denominator, not
0% method performance. CoPE and FSR-PC must not be called equivalent or unequal
from this preflight.

Once a credential is supplied securely, the frozen four-pair smoke may run.
Expansion to the remaining eight pairs is allowed only if every smoke fairness
check passes and all eight provider calls return without outage or timeout.

Even after a completed provider run, a higher CoPE valid rate would support only
generation factorization/assurance or efficiency. It would not show stronger
execution expressivity or embodied task success. Equivalent native results
would weaken the broad necessity claim. Oracle-correct but low native results
would be attributed to generation/provider behavior, not a controller.
