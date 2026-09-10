# Experiment-1 trace contract v1 freeze report

Status: `EXP1_INTERFACE_CONTRACT_FROZEN` after the tagged commit passes the
listed tests. `EXP1_TASK_CATALOG_FROZEN=false` and
`EXP1_FORMAL_TRACE_DATA_AVAILABLE=false`; neither blocks the interface freeze.

The contract supplies eleven named immutable records, eight checked-in JSON
schemas, eleven canonical fixtures, exclusive canonical exporters/readers, and
a recursive leakage scanner. `RuntimeTraceBundleV1` holds only method-visible
state and a digest reference to its separately sealed outcome. The scanner
rejects nested and serialized canonical/gold/expected/simulator-truth data.

Compatibility tests project the existing repeated-v2 event, ledger, execution
context, progress, and planning-problem records into v1 without completing
omitted semantics. Patch operators produced by a method remain auditable public
outputs; expected/correct operator labels remain forbidden.

The frozen byte inventory is
`frozen/repeated_v2_trace_contract_v1/HASH_MANIFEST.json`. The contract commit is
tagged `exp1-trace-contract-v1`; the exact commit and remote tag are verified
after commit creation. This report contains no claim that a task catalog,
production provider, pilot, or formal dataset is available.
