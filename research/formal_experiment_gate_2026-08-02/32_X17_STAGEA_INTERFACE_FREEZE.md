# X17 Stage A structured-interface freeze

Date: 2026-08-03 (Asia/Shanghai)

Stage A is exploratory interface qualification and cannot alter X16's negative
confirmatory result. It deterministically selects the first six APPLY templates
in the frozen X16 manifest order. These cases are development cases and are
excluded from any future X17 confirmatory holdout.

Four arms receive identical common input:

1. CoPE with an exact operation JSON schema and semantic operation labels;
2. the same typed fields with deterministically permuted neutral labels;
3. compact TX with exact `{op,path,value}` syntax and stable-ID path grammar;
4. FSR-PC with an exact complete-state JSON schema.

Each arm is run once with a fully explicit plain JSON contract and once with
OpenRouter strict `json_schema` structured output. The structured route sets
`provider.require_parameters=true`; an unsupported route must fail instead of
silently dropping the treatment. Official model metadata was checked before
freeze and listed `structured_outputs`, `response_format`, `tools`, and
`tool_choice` for `qwen/qwen3.5-flash-02-23`.

Frozen settings are reasoning `none`, temperature 0, seed 20260803, 8192 equal
completion tokens, 90-second timeout, zero retries, zero repair, and zero
fallback. Results are assignment-retaining. Raw responses are journaled before
scoring files are emitted.

Stage A passes only if each structured sparse arm—CoPE, neutral typed, and
compact TX—reaches at least 4/6 correct APPLY transitions. FSR-PC is reported
but is not part of the sparse-interface qualification threshold. A pass permits
construction of a newly frozen independent holdout; it is not paper evidence.

No simulator, GPU, robot action, development LIBERO state, or reserved state is
used.
