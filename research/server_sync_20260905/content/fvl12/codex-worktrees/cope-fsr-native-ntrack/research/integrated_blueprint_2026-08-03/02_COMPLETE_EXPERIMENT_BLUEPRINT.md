# Complete CoPE experiment blueprint

## 1. Causal question

The main experiment must isolate the recovery-state representation, not compare
unmatched robot systems:

> Given identical observations, event, history, progress, provider, validator,
> compiler, skills, controller, and seed, does an event-bound typed commitment
> proposal improve first-pass semantic generation and downstream recovery over
> a generic sparse transaction and full-state rewrite?

The assurance question is separate:

> Which illegal commission edits are stopped locally, which omissions require
> decomposed completeness checks, and which bad states can still publish?

## 2. Four evidence tracks

### Track A — matched-provider native output

Methods: CoPE-G, Compact-TX, FSR-PC. Oracle outputs are transport controls only.

- Start with the frozen four-triplet smoke, then 12 triplets, then a 60-case
  corpus only if provider availability and fairness gates pass.
- Same model, temperature, seed, max tokens, timeout, retry=0, repair=0, call
  budget, common input bytes, and rotating call order.
- Primary: first-pass semantic-valid and correct rate.
- Secondary: parser/native/decomposed rejection layer, proposal bytes,
  prompt/completion tokens, latency, unauthorized edit, progress corruption,
  continuity error, and omission error.
- A missing credential or outage is configuration/provider failure, not 0%
  method performance.

Current state: framework fair on 12/12 triplets and mocked transport 36/36;
real provider calls=0, so no learned result exists.

### Track B — oracle semantic-to-execution bridge

Methods: no-edit, current-world replan, CoPE-G, Compact-TX, FSR-PC, oracle-full.

All semantic methods receive the same correct event interpretation. This track
tests materialization, validation, compilation, action cancellation/continuity,
skill execution, and rejoin. It cannot establish representation-generation
superiority.

Required event families:

1. cancellation with no new action;
2. replacement requiring a new target/action;
3. temporary override followed by release/restoration;
4. irrelevant world change;
5. executing-action conflict versus legal continuity.

Use early, middle, and late timing, with at least one pre-event achieved
milestone and method-blind sibling/target assignment.

### Track C — learned end-to-end recovery

Use the same three native-output arms and common clean-qualified controller.
No oracle semantic proposal enters the method arms.

For every disturbed episode, run a paired clean shadow from the same initial
state and seed. Never filter the assigned denominator after observing reach,
provider validity, or controller behavior.

Primary endpoint: terminal current-goal success over all assigned episodes.

Key secondary endpoints:

- `P(disturbed success | paired clean succeeds)` as a ceiling diagnostic, not a
  replacement for the unconditional primary;
- valid-progress retention fraction;
- unsafe/obsolete action execution after event;
- reach-event, proposal parsed, native guard passed, decomposed validator
  passed, plan compiled, repair action executed, and terminal success cascade;
- normalized recovered fraction
  `(method - no_edit) / (oracle_full - no_edit)`, reported only when the paired
  oracle denominator is positive.

### Track D — assurance and falsification

Retain X14--X18 as mechanism evidence. Add held-out task schemas and
property-based multi-edit generation. Do not mix these rows with robot success
rates.

## 3. Clean-ceiling admission rule

Before any method comparison, qualify each task, controller/checkpoint, and
original/updated-goal variant on 30 independent clean episodes.

Admission requires both:

- at least 25/30 terminal successes (83.3%); and
- the two-sided 95% Wilson lower bound at least 0.65.

The same gate applies to ReKep, OpenVLA, the skill controller, and every other
backend. A method failing the gate is reported in a qualification table and is
not used to support semantic-recovery superiority on that cell. Do not tune the
gate after seeing method comparisons.

Why this solves the 30% problem: a low-clean system is excluded before disturbed
outcomes are seen, while paired clean shadows and unconditional assigned
success still expose residual execution ceilings.

If fewer than four task/updated-goal variants pass, stop the broad efficacy
route. Continue only a narrow mechanism/assurance paper or change the common
controller in a newly preregistered study.

## 4. Tasks and events

Minimum paper corpus:

- four task families, not four initial states of one task;
- at least four semantic stages per task;
- at least one irreversible or progress-bearing milestone before interruption;
- replacement, cancellation, override/release, and irrelevant-change families;
- early/middle/late event timing;
- one repeated or compound event setting held out from validator development.

Do not count state seeds as task breadth. LIBERO is acceptable for a narrow
paper; retain “long-horizon” in the title only if the admitted tasks actually
contain deep staged commitments and retained progress.

## 5. Sampling and statistics

Use a blinded pilot that is separate from paper episodes to estimate the paired
discordant rate for CoPE-G versus Compact-TX and FSR-PC. Freeze the final number
with 80% power, two-sided familywise alpha 0.05, and a smallest relevant paired
difference defined before the pilot is unblinded. Use a minimum of 30 and a
maximum of 100 paired seeds per task-event-timing stratum.

Analysis:

- paired binary endpoint: exact McNemar test and paired risk difference with
  confidence interval;
- progress fraction: paired bootstrap, resampling at task then seed level;
- familywise primary comparisons: Holm correction for CoPE-G vs Compact-TX and
  CoPE-G vs FSR-PC;
- task/event/timing results shown separately; pooled models include task as a
  cluster, never treating all seeds as independent task evidence;
- report Wilson intervals for every assigned success rate;
- missing/corrupt episode counts as primary failure and receives a separate
  failure category.

No superiority test should be run on the 12-case synthetic native-output pilot.

## 6. Failure taxonomy

Every episode receives exactly one earliest primary failure stage and any later
diagnostic flags:

1. configuration/provider unavailable;
2. event not reached;
3. provider timeout/outage;
4. response parse/schema failure;
5. native representation guard rejection;
6. decomposed validator rejection, with named predicate groups;
7. compiler/plan infeasible;
8. unsafe obsolete action continued;
9. skill/controller execution failure;
10. terminal goal failure despite valid recovery;
11. success.

This decomposition prevents a low-level controller miss from being reported as
a semantic-representation failure.

## 7. Required ablations

- CoPE exact oracle guard versus CoPE-G generic interpreter (upper bound only);
- typed operation-local guards removed one group at a time;
- decomposed completeness groups removed one at a time;
- persistent progress/history removed;
- stable IDs replaced with positional references;
- event/version binding removed;
- sparse proposal versus full rewrite under identical validator;
- canonical ordering enforcement versus order-insensitive normalization;
- decomposed validator versus exact full-state oracle control;
- single versus repeated/compound interruptions.

X17 shows every current predicate group has an isolated necessity example; that
does not replace embodied or held-out ablation.

## 8. Stop rules

- Provider credential absent: zero calls and configuration-blocked ledger only.
- Smoke fairness mismatch or provider outage: do not expand.
- Controller or updated-goal clean gate fails: do not run/interpret disturbed
  superiority for that cell.
- Any caller mutation, partial publication, or dangerous validator blind spot:
  stop the affected run, preserve it, diagnose, and version the correction.
- CoPE-G equals Compact-TX on learned validity and embodied outcomes: drop the
  CoPE-specific generation claim; retain only measured audit/assurance or cost
  differences.
- Compact-TX beats CoPE-G: redesign the typed interface or narrow the paper;
  do not remove the baseline.
- FSR-PC/Compact-TX/CoPE-G all fail while oracle-full succeeds: provider
  generation problem.
- All arms including oracle-full fail: controller/task substrate problem.

## 9. Artifact contract

For every episode retain:

`event -> common RecoveryInput hash -> native proposal/response hash -> parser -> native materializer receipt -> decomposed predicate violations -> committed state hash -> compiled repair -> preserved/cancelled actions -> controller trace -> terminal predicates`.

Also retain model/checkpoint, code commit, task asset hashes, initial state, seed,
call order, budgets, provider status, simulator state hash, RGB hash, and an
assigned-denominator row even if no method call occurs.

