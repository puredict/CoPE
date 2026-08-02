# X15 result: typed operations block commission errors, not omissions

Date: 2026-08-03 (Asia/Shanghai)

## Bottom line

After removing CoPE's exact `expected_patch` comparison, a generic typed
operation interpreter still rejected every one of the 14
commission/structural fault assignments before the common validator. Compact
TX materialized bad candidates for 5/14 and FSR-PC for 10/14.

But on eight partial or whole-operation omissions, all three non-oracle methods
materialized a wrong candidate in 8/8 cases. Typed operations constrain what an
output may do; they do not prove that it did everything the event requires.

The defensible architecture is therefore two-layer:

1. typed, event-bound operations and local preconditions reduce the commission
   error surface;
2. an independent completeness validator is still mandatory for omissions.

## Four-arm audited result

| Representation fail-open before common validator | CoPE exact control | CoPE generic typed | Compact TX | FSR-PC |
|---|---:|---:|---:|---:|
| All 22 faults | 0 | 8 | 13 | 18 |
| 14 commission/structural faults | 0 | 0 | 5 | 10 |
| 8 omission faults | 0 | 8 | 8 | 8 |

The exact CoPE arm is an oracle upper bound, not a fair deployment arm. Its 0/22
depends on comparing the proposal with a precomputed exact answer.

Full-pipeline controls:

- clean canonical outputs: 48/48 passed;
- faulty proposals: 88/88 changed from canonical;
- faulty cells: 88/88 rejected by the complete pipeline;
- end-to-end fail-open: 0/88;
- uncaught crashes: 0/88;
- caller-state mutations: 0/88;
- independent CSV-only audit: 19/19 checks passed;
- focused tests: 8 passed in 0.28 seconds;
- complete repository regression: 417 passed in 47.02 seconds.

The generic interpreter's source audit found no reference to
`expected_patch`, `derive_post_state`, or `validate_and_compile`. No provider,
credential, LLM, GPU, simulator, robot, or reserved LIBERO state 27--49 was
used.

## What the generic typed layer actually enforces

It accepts only a bounded typed-operation list and checks:

- event and input-state version binding;
- issuer authority and duplicate-event status;
- operation type licensed by the event type;
- exact operation fields;
- target, replacement, and override stable IDs;
- lifecycle and action-local preconditions;
- duplicate operations;
- atomic local effects such as replacement entity creation and override
  restoration bookkeeping.

It deliberately does not compare the patch or candidate with the full correct
answer. This makes the omission failure real rather than hidden by an oracle.

## Interpretation

The result preserves a narrower, technically meaningful CoPE argument:

> An event-bound typed commitment-edit language can make many unauthorized or
> malformed state changes unrepresentable or locally rejectable, reducing
> commission errors relative to generic path writes and full-state generation.

It does not support:

- typed operations guarantee complete recovery edits;
- CoPE is end-to-end safer than compact TX or FSR-PC in this experiment (all
  complete pipelines were 0/88 fail-open);
- exact-patch comparison is a fair implementation advantage;
- these hand-designed synthetic faults predict learned-model or robot success.

The comparison also confirms that compact TX is a strong baseline: its
allowlisted paths, event/version binding, duplicate-path check, and stable-ID
materializer rejected substantially more commission faults than FSR-PC.

## Paper and baseline consequence

The main safety story should no longer be “typed patch is safe.” It should be:

> CoPE decomposes assurance into local prevention of illegal commitment edits
> plus independent detection of missing required consequences.

Future learned-provider experiments must retain four conceptual controls:

- CoPE generic typed proposal;
- compact TX sparse proposal;
- FSR-PC full-state proposal;
- an oracle/exact arm only as a labeled upper bound, never as the primary CoPE
  result.

## Required next experiment

The current common validator still compares the whole candidate with a fully
known oracle state. Replace it with decomposed, implementation-independent
completeness predicates derived from the event contract: required lifecycle
effect, version/evidence update, goal consistency, progress preservation, and
action continuity. Then repeat the omission suite and measure which checks are
necessary and sufficient. Without that step, the second safety layer is still
oracle-confounded.

