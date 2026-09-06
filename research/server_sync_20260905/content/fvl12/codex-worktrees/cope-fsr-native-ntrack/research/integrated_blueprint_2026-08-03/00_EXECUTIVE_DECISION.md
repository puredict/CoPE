# CoPE baseline and experiment decision after X10--X18

Date: 2026-08-03 (Asia/Shanghai)

## Decision

The final mandatory comparator set is no longer just CoPE versus FSR-PC. It is:

1. **CoPE-G**: generic typed commitment operations, with no exact-patch oracle;
2. **Compact-TX**: generic allowlisted path/value transaction;
3. **FSR-PC**: full canonical state rewrite with plan continuity;
4. **No-edit/current execution**: negative control;
5. **Current-world replan**: strong behavior-level replanning control;
6. **Oracle-full / CoPE-exact**: labeled upper bound only.

CoPE-G, Compact-TX, and FSR-PC must receive the identical semantic input,
provider, model/sampling budget, decomposed validator, compiler, skill library,
controller, observation, and episode seed. Omitting Compact-TX is no longer
defensible: it matched all 12 semantic transitions and was smaller than FSR-PC
on 12/12 cases.

## Why ReKep is not the primary baseline

The reported/reproduced ReKep clean success is about 30%. That makes disturbed
success uninterpretable as a test of CoPE's recovery representation: most
failures can occur before or outside recovery. ReKep remains a published
geometric secondary only on cells where its own clean qualification passes the
same gate as every other method.

OpenVLA is also not currently a valid semantic-replacement substrate:

- task-1 clean calibration: 5/5, but oracle updated-goal replacement: 0/5;
- task-5 front/left/right counterfactual targets: 0/4;
- task-7 clean: 2/5.

The parameterized skill controller is the current mechanism-test substrate
because fresh states 15--24 passed 10/10 provisionally. It does not establish a
learned-policy result and must itself pass a larger clean and updated-goal gate
before paper episodes.

## What the recent falsification chain changed

- X11: a generic transactional executive was semantically equivalent on 12/12;
  unique CoPE expressivity is rejected.
- X12: compact generic transactions were below FSR size on 12/12; generic sparse
  output is not unique. CoPE was smaller on only 8/12 overall.
- X13: the fair learned comparison became tri-arm, but credential preflight made
  zero provider calls; no learned ranking exists.
- X14: the original CoPE safety advantage came from exact `expected_patch`
  comparison; typing-specific attribution failed.
- X15: after removing that oracle, typed operations produced 0/14 commission
  fail-opens versus 5/14 Compact-TX and 10/14 FSR-PC, but all non-oracle methods
  failed 8/8 omission probes before the common validator.
- X16: eight decomposed event-contract groups accepted 48/48 clean and rejected
  39/39 materialized faulty candidates without full-state oracle equality.
- X17: all 64 first- to third-order predicate compositions were rejected with
  exact group attribution; every predicate had an isolated necessity example.
- X18: a structure-agnostic pass found four real unknown-field blind spots in
  2,352 mutations. The preserved v1 failed; a minimal schema repair made v2 pass
  with zero dangerous blind spots. Fourteen order-only hash/canonicalization
  divergences remain explicit.

## Current paper route

**Conditional go for a narrow assurance/factorization paper; no-go for an
end-to-end superiority claim today.**

The most defensible target claim is:

> Event-bound typed commitment operations reduce the commission-error surface
> relative to generic sparse and full-state outputs, while decomposed contract
> validation is required to detect omitted consequences before publication.

This claim still needs a real learned-provider generation result and embodied
validation on clean-qualified tasks. Until then, the evidence-safe statement is
that the architecture passes synthetic conformance and falsification tests.

Do not claim unique sparse expressivity, universal size advantage, inherent
typed safety, learned superiority, robot recovery success, or long-horizon
generalization from the current evidence.

