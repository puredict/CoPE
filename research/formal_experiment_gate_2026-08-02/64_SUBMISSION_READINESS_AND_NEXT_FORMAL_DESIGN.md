# CoPE submission readiness and next formal experiment design v6

Date: 2026-08-04 (Asia/Shanghai)

## Bottom line

**The common-prefix controller problem is resolved for future experiments, but
the CoPE paper claim is not yet proven.**  The decisive remaining uncertainty
is method-level: on the existing simple single-interruption cases, CoPE and the
strong neutral patch arm have identical embodied endpoint success.  More runs
of that same design will not establish that persistent typed commitment editing
is necessary.

The idea remains submission-viable because the existing evidence establishes
implementation correctness, scaling behavior, learned high-level proposals and
a now independently validated physical substrate.  A defensible ICRA/CoRL
claim requires a fresh confirmatory experiment where repeated interruptions
create dependent persistent commitments and where every baseline is first
shown capable of expressing the correct answer.

## What was resolved in this cycle

| Evidence | Result | Interpretation |
|---|---:|---|
| Baseline prefix diagnostic, task-1 states 5--14 | 10/10 | Historical centered controller is not broadly broken |
| Natural development legacy vs candidate, states 0--4 | 5/5 vs 5/5; all action hashes equal | Opt-in fallback does not alter successful historical traces |
| Underpowered `+40 mm` stress, states 0--4 | 5/5 vs 5/5 | Retained negative result; perturbation was inside the grasp region |
| `+80 mm` development stress, states 0--4 | 0/5 vs 5/5 | Bounded relocalize-and-regrasp executes after `grasp_not_acquired` |
| Locked natural validation, states 15--24 | 10/10 vs 10/10; all action and simulator hashes equal | Independent non-regression passed |
| Locked `+80 mm` validation, states 15--24 | 0/10 vs 10/10; 10 candidate wins, 0 losses | Independent recovery validation; exact two-sided p=0.001953125 |
| Repository regression | 501/501 tests pass | Controller change and historical provenance compatibility pass |

All experiments above used CPU, zero provider calls, and did not index task-1
states 25--49.  State 33 was not retried.  The 80-mm stress is a controlled
substrate perturbation, not a claim to reconstruct the unseen geometry that
caused state 33.

## Scientific status of the current paper claim

### Supported

- A typed CoPE operation can update persistent commitments atomically while
  preserving completed physical progress.
- The shared commit envelope, validators, receipts and replay evidence are
  implemented and tested.
- CoPE scales better than the current FSR-PC implementation on synthetic large
  commitment states.
- In the retained formal segment, CoPE and neutral patch both reached 12/12
  embodied endpoints while compact and FSR-PC reached 0/12.
- The repeated state-33 stop was a pre-method substrate failure, not a CoPE
  failure, and is no longer an unresolved engineering blocker for a new study.

### Not yet supported

- CoPE has not beaten the strongest equal-capability neutral patch baseline.
- The compact/FSR 0/12 result is vulnerable to the criticism that interface and
  validator restrictions—not the conceptual recovery strategy—caused failure.
- The interrupted state-27--46 run is descriptive, not confirmatory.
- Existing learned embodied evidence is concentrated on one LIBERO task and
  simple single replace/cancel events.
- The bounded regrasp validation supports the shared event constructor only; it
  contributes no treatment advantage to CoPE.

Therefore the honest readiness label is **GO for a new decisive formal study;
NO-GO for claiming the paper's central empirical result is already complete.**

## The next decisive experiment

### Research question

When two interruptions sequentially modify dependent, persistent task
commitments after physical progress has been made, does typed constraint-state
patch editing reduce invalid intermediate states and stale execution compared
with equally expressive patching and full-state regeneration?

### Fresh task pool

Use basket tasks with the same physical skill family but fresh task identities:

- LIBERO-10 task 0: alphabet soup and tomato sauce to basket;
- LIBERO-10 task 7: alphabet soup and cream cheese to basket.

Task 1 remains development-only.  Its states 25--49 stay locked.  For each new
task, freeze states 0--9 for controller/interface development, states 10--29
for confirmatory execution, and states 30--49 as permanent reserve.  No formal
state may be opened until task-specific prefix feasibility passes on 0--9.

### Event sequences

Each base state receives two separately reset, preregistered sequences:

1. `replace_then_cancel`: complete object A, replace pending B with C, then
   cancel C before execution;
2. `replace_then_replace`: complete A, replace B with C, then replace C with D
   while preserving A and invalidating every stale B/C commitment.

Replacement objects must be present in the scene and frozen from a task-specific
symbol manifest before any provider call.  The second event is built from the
post-first-event committed state, not from the original prompt.

### Arms

1. **CoPE:** typed local commitment operations with transaction receipt;
2. **Neutral patch:** equally expressive JSON patch over the same commitment
   state, same evidence and same semantic validator;
3. **Fair FSR-PC:** regenerate the full commitment state using an explicit,
   documented schema and the same lifecycle invariants;
4. **Full replan:** regenerate the remaining ordered commitments while treating
   completed physical facts as immutable evidence.

Model, system context, evidence bytes, temperature, seed, call budget, retry
budget and output-token ceiling are matched.  Compact/FSR may not be assigned a
hidden allowlist or exact-cardinality requirement absent from its prompt.

### Mandatory zero-provider interface gate

Before spending a model call, feed each arm canonical oracle-correct outputs for
every event family.  Every arm must:

- parse and validate the intended correct state;
- preserve the completed commitment and physical predicate;
- remove all superseded commitment IDs;
- compile to the same physical directive or HALT;
- execute the same correct oracle-selected object from identical reset;
- expose no arm-specific structural blocker.

If an arm cannot pass, repair its interface using development states only and
repeat the zero-provider gate.  Do not count interface incompetence as a formal
method failure.

### Confirmatory unit and denominator

The independent unit is a full two-event sequence.  Two tasks x 20 formal
states x 2 event sequences yields **80 sequences per arm** and **320 fixed
provider calls** for four arms, with zero retry/repair calls.  Prefix failure is
recorded once at sequence level before arm allocation and stays in a separate
substrate denominator; no method call is made if the shared event constructor
fails.

### Primary endpoint

Sequence-level success requires all of the following:

1. both proposed updates parse and validate;
2. no invariant violation at either intermediate committed state;
3. completed physical progress remains true after each patch;
4. no superseded B or C commitment is executed;
5. the final intended object predicate or HALT condition is satisfied;
6. action, call and horizon budgets are respected.

Primary comparison: CoPE vs neutral patch, paired over the same 80 sequences,
two-sided exact McNemar test with Holm correction for the prespecified secondary
method comparisons.  Report effect size and exact confidence interval, not only
p-values.

### Secondary endpoints

- any intermediate invariant violation;
- stale-commitment execution;
- valid completed progress retained;
- edit locality / number of commitment fields changed;
- proposal bytes, prompt/completion tokens and latency;
- post-interruption physical action count;
- fail-closed rate and failure class;
- shared-prefix construction actions and any regrasp activation, reported
  separately from method cost.

## Stop/go rules

- **Stop before formal calls** if task-0/task-7 prefix development is not 20/20
  or any method fails the oracle-correct interface gate.
- **Stop the run** on configuration hash mismatch, unexpected credential
  behavior, arm-order divergence, state outside the authorized set, retry, or
  journal corruption.
- **Do not stop for observed treatment outcomes.** Execute all 320 calls and
  all authorized sequences unless an integrity stop occurs.
- **Submission GO:** CoPE beats neutral patch on the primary endpoint with a
  practically meaningful paired effect, while not increasing stale execution
  or invariant violations; at least one efficiency/locality endpoint also
  favors CoPE.
- **Reframe rather than oversell:** if CoPE ties neutral patch again, position
  the contribution as a verifiable transaction/assurance framework only if it
  provides clear invariant, auditability or efficiency gains.  Without those
  gains, the current central idea is not yet a strong method paper.

## Immediate execution order

1. implement task-parameterized commitment/object manifests for tasks 0 and 7;
2. implement and test the zero-provider four-arm oracle-correct interface gate;
3. audit task-specific shared prefixes on states 0--9 only with the validated
   bounded-regrasp substrate;
4. freeze case manifest, configs, hashes, arm order and exact analysis script;
5. perform a credential-free cold preflight proving zero formal state access;
6. only then authorize the new 320-call formal experiment.

