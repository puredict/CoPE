# X16 independent-semantic-task preregistration

Frozen: 2026-08-03 (Asia/Shanghai), before any provider call and before any
model output exists. X16 is a synthetic semantic experiment. It does not use a
GPU, simulator, robot, OpenRouter, development state, or reserved state.

## Question and claim boundary

X14 contained 60 cells but only 12 transition templates, each repeated with
five context variants. Its 28/60 CoPE versus 18/60 compact-TX difference was
not significant at the independent-template level. X16 asks whether CoPE has a
higher probability than compact TX of producing a first-pass correct semantic
decision across genuinely different transition logics.

The independent and inferential unit is one X16 task template. X16 has 36 such
units and no context variants. Case IDs, object names, and extra context never
create additional observations. A result can support a representation-level
semantic-generation claim on this frozen synthetic corpus, not embodied task
success, universal recovery superiority, or access to reserved states.

## Corpus and independence admission rule

The manifest contains 36 templates: two templates for each of the 17 required
families and two additional compound atomic transitions. Every required family
therefore has balanced primary coverage. The outcome distribution is 22 APPLY,
4 NO_OP, 6 REJECT, and 4 ABSTAIN.

A template is admitted only if its normalized logic signature is unique across
the corpus. The signature includes event class, authorization/version premise,
dependency topology, affected commitment set, operator sequence, continuity
effect, progress effect, concurrency relation, and disposition. Changing only
names, object IDs, state versions, or irrelevant context does not change this
signature and cannot create another unit. The manifest records why every task
is not the same transition as its closest X14 template.

Required coverage is: cancellation, override, release, world-change release,
replacement, stale version, idempotence, unauthorized mutation, continuity
conflict, continuity-valid recovery, multi-commitment dependency, partial
progress preservation, concurrent external event, obsolete replacement,
already-satisfied goal, contradictory observation, and irrelevant-state
scaling.

## Four frozen dispositions

- `APPLY`: exactly one persistent-state transition is licensed; emit it.
- `NO_OP`: the event is valid but creates no semantic state change.
- `REJECT`: the event is unambiguously invalid under version, authority,
  identity, scope, or candidate-validity rules.
- `ABSTAIN`: the evidence is insufficient or contradictory, so no unique safe
  transition is licensed; stop conservatively.

NO_OP, REJECT, and ABSTAIN are separately scored. Collapsing them into one empty
patch is incorrect even though all three preserve the pre-state. REJECT and
ABSTAIN must compile to a stop decision; NO_OP may continue an already-valid
action. APPLY increments the state revision exactly once and records the event.

## Arms and information fairness

All three arms receive byte-identical canonical common input: case ID, original
task, complete pre-state, complete event, task policy, the common disposition
definitions, common safety rules, and common reason-code vocabulary. Only the
last output-contract message differs:

1. CoPE emits a minimum ordered typed persistent-state patch.
2. compact TX emits a minimum ordered generic path/value transaction and is
   forbidden from using CoPE operation names.
3. FSR-PC emits the complete canonical post-decision state.

All arms expose the same disposition and reason code. No arm receives the
oracle, post-state hash, expected directive, family label, X14 comparison, or
scoring result. Normalized provider requests must be identical after replacing
the final representation contract with one placeholder. A failed fairness
check blocks all calls.

## Frozen provider and execution contract

- model: `qwen/qwen3.5-flash-02-23` through the same OpenAI-compatible provider
  adapter used by X14;
- reasoning effort: `none`;
- temperature: 0;
- seed: 20260803;
- maximum prompt tokens: 16,000;
- maximum completion tokens: 8,192 for every arm;
- timeout: 90 seconds;
- retries: 0; repair: 0; fallback: 0; oracle substitution: 0;
- response format: one JSON object;
- task order: manifest order;
- within-task arm order: the frozen seed-generated table in
  `03_X16_ARM_ORDER.csv`, balanced 12/12/12 at each of the three positions.

The larger common completion ceiling is frozen before outcomes to avoid making
FSR-PC truncation the intended treatment. Actual token and byte costs remain
secondary outcomes.

## Frozen validator and oracle qualification

The validator source is `04_X16_QUALIFICATION_PROGRAM.txt`. It parses exact
arm schemas, checks disposition and reason code, checks event and base-version
binding, materializes CoPE and compact-TX outputs, checks that non-APPLY outputs
cannot mutate state, and compares the resulting canonical state to the frozen
oracle. It also checks three-arm state equivalence, common-input hashes,
normalized requests, hidden-answer keys, unique logic signatures, and arm-order
balance. It does not derive the expected decision from provider output.

Before provider use, every one of the 108 arm/case oracle candidates must:

1. parse under its arm contract;
2. express the frozen disposition and reason code;
3. materialize to the same frozen post-state as the other two arms;
4. be accepted by the common decision/state validator;
5. share the exact common input and normalized request with its triplet;
6. pass hidden-answer and arm-specific-information checks.

Any failure is retained, reported, and blocks provider execution. Qualification
does not count as learned evidence.

## Scoring

Primary outcome is first-pass semantic correctness, one binary value per arm
per independent template. A cell is correct only if the provider call succeeds,
the exact arm schema parses, disposition and reason code equal the oracle, the
proposal is event/version bound, its materialized canonical state equals the
oracle, and the common validator accepts it. For NO_OP, REJECT, and ABSTAIN the
state must remain byte-canonically unchanged. A parser failure, timeout,
truncation, wrong disposition, wrong reason, extra mutation, omitted mutation,
or invalid schema is incorrect. No partial credit is used in the primary test.

Secondary outcomes are correctness by family and disposition, FSR-PC
correctness, unsafe-mutation counts, wrong-stop/no-stop taxonomy, completion
tokens, proposal bytes, and latency. These cannot replace or redefine the
primary outcome.

## Exclusions and missingness

The primary analysis is assignment-retaining: all 36 templates and all three
assigned cells remain. Provider timeout, parse failure, and arm-specific outage
are failures, not exclusions. A triplet is not run if its pre-call fairness or
oracle qualification fails. A discovered corpus-construction defect,
non-identical common input, corrupted oracle, or provider-wide incident that
makes the run uninterpretable blocks the whole run and requires a newly named,
re-frozen experiment; it is not repaired or selectively excluded after seeing
answers. There are no post-outcome template exclusions.

## Primary statistical test

The single primary contrast is CoPE versus compact TX. Let `b` be the number of
independent templates on which CoPE alone is correct and `c` the number on which
compact TX alone is correct. The primary test is the two-sided exact McNemar
test, equivalently an exact binomial test of `b ~ Binomial(b+c, 0.5)` conditional
on discordance. Ties are retained in rates but do not enter the conditional
test. Alpha is 0.05. The direction must satisfy `b > c`.

A positive confirmatory conclusion additionally requires no excess CoPE unsafe
mutation count versus compact TX. If the exact test is not significant, the
result is inconclusive or negative regardless of cell-level rate. FSR-PC
comparisons and family decompositions are secondary; Holm correction is used
if inferential p-values are reported for both secondary pairwise contrasts.

## Sensitivity and interpretation

With only 36 independent templates, significance depends on both the number and
imbalance of discordant pairs. The exact threshold and unconditional power grid
are frozen in `07_X16_POWER_SENSITIVITY.csv`. At least six discordant pairs are
needed for any two-sided result below 0.05, and all six must favor CoPE. Examples:
9 discordant pairs require at least 8 CoPE-only wins; 12 require 10; 17 require
13; 20 require 15; 24 require 18; 30 require 21; and 36 require 25. Thus 36
templates can support a meaningful strong asymmetry, but it is not an 80%-power
design for modest advantages unless discordance is common.

## Freeze and stopping rule

The manifest, oracle, validator/program, common prompt and arm contracts,
arm-order table, seed, scoring, exclusions, and primary test are frozen by the
SHA-256 ledger before any provider call. X16 stops after qualification in the
current stage. No OpenRouter call is authorized by this document alone; a later
provider run must first verify the freeze ledger and repeat qualification with
no changed locked input.
