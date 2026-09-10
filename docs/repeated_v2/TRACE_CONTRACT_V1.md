# Experiment-1 trace contract v1

`cope-exp1-trace-contract/v1` is the stable, read-only interchange boundary exported
by Experiment 1. Experiment 2 may consume this interface independently of task
catalog eligibility, pilot completion, or a positive Experiment-1 result.

## Records

The Python interface is
`cope_benchmark.repeated_v2.trace_contract_v1`. It freezes these record names:

- `RuntimeTraceBundleV1`
- `PublicEventEvidenceV1`
- `PersistentLedgerSnapshotV1`
- `ExecutionContextSnapshotV1`
- `ProposedPatchRecordV1`
- `AcceptedPatchRecordV1`
- `PlanningProblemV1`
- `ProgressCertificateV1`
- `ActionTraceReferenceV1`
- `SealedOutcomeV1`
- `OccurrenceAllocatorVersionV1`

All records are recursively immutable after construction. Serialization uses
the repository's canonical UTF-8 JSON convention: object keys are sorted,
arrays preserve order, non-finite numbers and duplicate keys are rejected, and
files contain one terminal newline. SHA256 values are computed over canonical
JSON bytes without that file newline.

`RuntimeTraceBundleV1` carries public observation/evidence references, public
user language, each method's own accepted ledger and execution context,
proposed and accepted patches, compiled planning problems, planner decisions,
skill calls, learned-policy action-trace references, public runtime-verifier
outputs, and progress certificates. It contains only a hash reference to the
separately stored `SealedOutcomeV1`.

## Public and sealed boundary

The public bundle cannot contain hidden canonical event cause, canonical event
family, an expected operator, a gold occurrence, a canonical planning problem,
the correct responsibility route, an oracle correction packet, a method-result
label, or simulator state unavailable to the agent. Canonical event-family
labels are also forbidden in string values so a serialized nested object cannot
bypass the boundary.

Method-generated patch operators are retained because they are observable
outputs under evaluation. Their presence is not an expected/correct operator
label. The recursive scanner in
`trace_contract_validation_v1.assert_no_hidden_leakage` checks mappings,
sequences, record instances, and strings containing serialized JSON.

`SealedOutcomeV1` belongs to the evaluator/harness. It records the final active
task result, unsatisfied active occurrences, wrong-occurrence execution,
completed-step regression, hard-constraint violations, event reachability,
timeout/manual-intervention flags, evaluator identity, and hidden-truth digest.
It is never embedded into the public bundle.

## Export and validation

`trace_exporter_v1` projects existing repeated-v2 public records without adding
missing goals, correcting occurrence identity, restoring forgotten progress, or
consulting task IDs and simulator truth. Writers use exclusive file creation so
an existing trace is not overwritten. Readers require canonical bytes and run
both the executable record invariants and checked-in JSON Schema validation.

The canonical core is the already frozen
`cope_benchmark.exp1_trace_contract_v1` package. This repeated-v2 binding adds
the requested action-trace and proposed/accepted-patch records without changing
the core version or public/sealed boundary. Its schemas are under
`schemas/repeated_v2/trace_contract_v1/`, and its canonical fixtures and byte
hashes are under `frozen/repeated_v2_trace_contract_v1/`. The immutable Git tag
`exp1-trace-contract-v1` identifies core commit
`1237de979fad501b2e1c730111160959a246bf96`; the v2.1 branch merges that commit
and records the binding byte hashes separately.

## Independent downstream gates

The former broad Experiment-1 dependency is represented by three independent
states:

- `EXP1_INTERFACE_CONTRACT_FROZEN`
- `EXP1_TASK_CATALOG_FROZEN`
- `EXP1_FORMAL_TRACE_DATA_AVAILABLE`

The interface gate depends only on this contract, schemas, fixtures, tests, hash
manifest, and tag. It does not depend on task eligibility, formal trace data, or
scientific success. Catalog and formal-data consumers must check their own two
gates separately.

## Compatibility policy

Existing `PublicEventPayload`, `PersistentLedger`, `ExecutionContext`,
`PlanningProblem`, and `ProgressCertificate` values can be projected into v1.
Projection preserves omissions and method errors. Any incompatible field change
requires a new contract version; v1 schemas and fixtures remain immutable.
