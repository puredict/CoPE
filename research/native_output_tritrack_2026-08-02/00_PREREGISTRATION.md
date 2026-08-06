# X13 tri-arm matched-provider native-output preregistration

Frozen date: 2026-08-02 (Asia/Shanghai)

## Motivation and claim boundary

X11 showed generic transactional equivalence; X12 showed an executable compact
generic transaction is smaller than FSR full state on 12/12 cases and that
CoPE is smaller than compact TX on only 8/12. A two-arm CoPE-vs-FSR provider
experiment would now omit a demonstrated strong sparse alternative.

This CPU/offline generation experiment therefore compares three native outputs
from the same frozen model and exact common `RecoveryInput`:

1. CoPE specialized typed minimum patch;
2. generic compact path/value transaction;
3. FSR-PC canonical full-state-v2 rewrite.

It does not run a robot, simulator, controller, planner, or GPU. A CoPE advantage
would support only learned-generation factorization/assurance or output-cost
claims. Compact-TX equivalence would further weaken CoPE specificity. No result
establishes embodied task success or unique execution expressivity.

## Frozen cases and stage gate

Use the same 12 public synthetic N-track cases and phase assignments as the
existing two-arm preregistration. Four smoke cases run first: no-op,
replacement, wrong-source revoke, and invalid action continuity. The remaining
eight run only if all 12 smoke arm calls return without provider outage/timeout
and all four triplets pass fairness. Method-invalid smoke output does not stop
expansion.

## Provider and sampling

- adapter: non-fake OpenAI-compatible chat-completions;
- endpoint: OpenRouter-compatible endpoint supplied by command line;
- model: `qwen/qwen3.5-flash-02-23`;
- temperature: 0.0;
- seed: 20260802;
- completion ceiling: 4096 for every arm;
- prompt ceiling: 12000 for every arm;
- timeout: 90 seconds;
- one call per arm/case;
- retries: zero;
- repair/feedback: zero.

Call order rotates by manifest index over `(CoPE, compact TX, FSR-PC)`, so the
12-case expansion has four occurrences of each first position. The four-case
smoke is necessarily not perfectly balanced; call order is retained in raw
results and never changed after outcomes.

Credentials are read only from the named environment variable. Missing
credentials stop before HTTP calls and retain all 36 assigned cells as
`configuration_blocked`; this is not 0% performance.

## Fairness contract

Within each triplet:

- exact canonical `RecoveryInput` payload and common-input message bytes match;
- model, temperature, seed, token ceilings, timeout, retry, and repair budgets
  match;
- normalized provider-visible request hashes match after replacing only the
  arm-specific output contract with one sentinel;
- no arm receives state outside `pre_state` already embedded in the common
  input;
- provider free-text controller commands are rejected and never executed.

The three output contracts may differ only to define their schemas. Contract
length and reported provider prompt tokens are measured, not forced equal.

## Compact output contract

The compact arm returns exactly:

```text
schema_version = generic-compact-transaction-v1
base_version
event_id
writes = ordered generic {op,path,value} records
```

Allowed paths and deterministic ordering are frozen in the contract. Before and
after hashes are executor-generated receipt fields, not model proposal fields.
The output uses no CoPE semantic operation names.

## Common evaluation

- CoPE: parse typed patch, independently materialize full canonical state;
- compact TX: parse and generically apply path/value writes to a deep copy;
- FSR-PC: parse complete full-state-v2;
- all three then enter the same event-bound semantic validator/compiler exactly
  once;
- publication occurs only after validation.

Mocked canonical transport controls must pass 12/12 triplets and 36/36 arm
cells before any real-provider result is eligible. They are tests, not model
samples.

## Outcomes

Primary descriptive outcome: first-pass semantic-valid and correct rate.

Required decomposition: parser failure, event/version/path rejection,
unauthorized or stale edit, progress corruption, continuity error, proposal
bytes, prompt/completion tokens, latency, validator calls, provider
outage/timeout, call order, and repair status (`not_enabled`).

No superiority hypothesis test is planned for 12 triplets. Counts and paired
differences are pilot estimates only.

## Stop and interpretation rules

1. Missing credentials: zero calls; configuration-blocked result only.
2. Any smoke fairness mismatch or outage/timeout: stop expansion.
3. Invalid method output does not stop expansion.
4. CoPE > compact TX and FSR-PC: supports only a specialized generation-bias
   claim pending larger paired corpus.
5. CoPE = compact TX: CoPE-specific generation claim weakens.
6. compact TX > CoPE: primary representation claim requires redesign or a much
   narrower typed-assurance argument.
7. Oracle controls correct with native arms low: provider-generation failure,
   not controller evidence.
8. No outcome unlocks LIBERO states 27--49.

