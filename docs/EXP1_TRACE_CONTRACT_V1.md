# Experiment-1 minimal read-only trace contract v1

This interface freezes only the serialization and public/sealed data boundary required by downstream experiments. It does not certify an Experiment-1 task catalog, a formal pilot, formal trace availability, task eligibility, or scientific success.

The frozen record set is `RuntimeTraceBundleV1`, `PublicEventEvidenceV1`, `PersistentLedgerSnapshotV1`, `ExecutionContextSnapshotV1`, `PatchRecordV1`, `PlanningProblemV1`, `ProgressCertificateV1`, and `SealedOutcomeV1`. The occurrence allocator is `cope-exp1-occurrence-allocator/v1`; canonical serialization is `cope-canonical-json/v1`.

`RuntimeTraceBundleV1` is public. It may contain only a SHA-256 reference to a sealed outcome, never the sealed object or causal labels. `SealedOutcomeV1` is stored and evaluated separately. Recursive structural checks reject hidden causes, oracle labels, responsible-module labels, correct patches/operators, simulator interventions, and serialized nested forms of those fields from public values.

The dependency state is deliberately split:

- `EXP1_INTERFACE_CONTRACT_FROZEN`: established by the tagged schema/hash set.
- `EXP1_TASK_CATALOG_FROZEN`: independent and not established by this interface freeze.
- `EXP1_FORMAL_TRACE_DATA_AVAILABLE`: independent and not established by this interface freeze.

The exporter reads a normalized source record, validates it, emits canonical bytes with exclusive destination creation, and can forbid all destination writes under declared Experiment-1 roots. It never edits its input.

All fixtures use `NOT_FORMAL_EVIDENCE` identifiers and exist only for compatibility testing.
