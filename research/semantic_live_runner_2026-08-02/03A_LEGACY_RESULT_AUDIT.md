# X04 V1 concurrent result audit

Date: 2026-08-02 (Asia/Shanghai)

Artifact: `03_ASSIGNED_RESULTS.csv`

SHA-256: `2927f2573770af75505054f11d02496568c69a6c5a11b3e6b13b29af897d32bf`

Observed result: 10/10 rows report `passed=True`, covering states 0--4 and
both frozen event types.  Rows contain non-test
`live_libero_eval_predicate` packets, production-validator truth
`done=True/pending=False`, byte-identical paired input hashes, equal native and
materialized full-state-v2 hashes, equal directives, provider-free accepted
patches, and zero reported post-event actions.

## Why this is retained but not accepted as the final X04 result

The run was launched concurrently from the earlier split implementation.  It
finished after the hardened implementation commit, so its file timestamp alone
cannot identify the code loaded by the already-running Python process.  The CSV
schema proves it is the earlier implementation because it lacks the hardened
fields `runtime_git_commit`, `case_manifest_sha256`,
`controller_config_sha256`, `stability_trace_sha256`, and separate before/after
mutation probes.

In addition, the earlier implementation supplied its simulator/action
"after" values to the semantic function before the semantic call, rather than
probing them after the call.  The semantic function is pure, but that ordering
does not satisfy the preregistered non-mutation evidence standard.

Therefore V1 is preliminary live evidence, not the gate result.  It is kept
byte-for-byte and will not be overwritten.  The hardened committed runner
`739e175521e93a8c598cdef20f5b0570f1809c81` must write a versioned V2 artifact
and independently meet all frozen gates.
