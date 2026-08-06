# X16 frozen prompt and arm contracts

## Provider-visible message 1: common system prompt

```text
You are a deterministic semantic state-transition generator. Use only the
supplied X16 recovery input. Distinguish APPLY, NO_OP, REJECT, and ABSTAIN under
the common semantic contract. Do not invent authority, event order, evidence
precedence, fallback commitments, progress, or world facts. Return exactly one
JSON object satisfying the final output contract, with no prose or Markdown.
```

## Provider-visible message 2: byte-identical common input

```text
X16_RECOVERY_INPUT_CANONICAL_JSON
<the exact common_input_json field for this case from
01_X16_INDEPENDENT_TASK_MANIFEST.csv>
```

The JSON contains only `schema_version`, `case_id`, `original_task`,
`pre_state`, `event`, `task_policy`, and `common_semantic_contract`. The latter
defines the four dispositions, common safety invariants, and the shared allowed
reason-code vocabulary. No family, oracle, expected output, post-state,
directive, arm label, score, or X14 comparison is included.

## Provider-visible message 3A: CoPE

```text
OUTPUT CONTRACT: X16 CoPE typed minimum patch v1.
Return exactly: schema_version, disposition, reason_code, base_version,
event_id, operations. schema_version is "x16-cope-patch-v1". disposition and
reason_code use the common semantic contract. base_version and event_id bind
the proposal to the supplied input. For APPLY, operations is the minimum
ordered list of typed persistent-state edits needed for the unique licensed
transition and ends with exactly one CommitEvent. Allowed typed operations are
SetCommitmentStatus, SetCommitmentField, InsertCommitment, SetAction,
InsertAction, SetProgress, InsertProgress, AddRestoration, RemoveRestoration,
SetFact, and CommitEvent, with the canonical fields demonstrated by the input
state schema. For NO_OP, REJECT, and ABSTAIN, operations is []. Do not emit
generic JSON paths, a full state, prose, or extra fields.
```

## Provider-visible message 3B: compact TX

```text
OUTPUT CONTRACT: X16 generic compact transaction v1.
Return exactly: schema_version, disposition, reason_code, base_version,
event_id, writes. schema_version is "x16-compact-tx-v1". disposition and
reason_code use the common semantic contract. base_version and event_id bind
the proposal to the supplied input. For APPLY, writes is the minimum ordered
list of generic {op,path,value} JSON edits. op is add or replace. Allowed paths
are /commitments/<id>/<field>, /commitments/+/<id>, /actions/<id>/<field>,
/actions/+/<id>, /progress/<id>/<field>, /progress/+/<id>, /restorations,
/facts/<key>, /processed_events/+/<event_id>, /state_version, and
/evidence_version. Stable IDs address records. For NO_OP, REJECT, and ABSTAIN,
writes is []. Do not use CoPE semantic operation names, emit a full state,
prose, or extra fields.
```

## Provider-visible message 3C: FSR-PC

```text
OUTPUT CONTRACT: X16 FSR-PC complete state v1.
Return exactly: schema_version, disposition, reason_code, base_version,
event_id, state. schema_version is "x16-fsr-pc-v1". disposition and
reason_code use the common semantic contract. base_version and event_id bind
the proposal to the supplied input. state is the complete canonical
x16-state-v1 post-decision state with every field and record. For NO_OP,
REJECT, and ABSTAIN, state exactly equals pre_state. Do not emit a patch,
generic writes, prose, or extra fields.
```

## Frozen request parameters and fairness normalization

Every request uses model `qwen/qwen3.5-flash-02-23`, reasoning effort `none`,
temperature 0, seed 20260803, maximum 16,000 prompt tokens, maximum 8,192
completion tokens, 90-second timeout, zero retries, zero repair, and JSON-object
response format. Fairness hashing replaces all of message 3 with the same
literal `<ARM_OUTPUT_CONTRACT>` and requires the remaining request to be
identical across the triplet.
