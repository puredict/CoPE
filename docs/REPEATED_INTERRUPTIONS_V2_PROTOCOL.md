# Repeated-interruption v2 protocol

The binding scientific protocol is preserved verbatim in
[01_FROZEN_SCIENTIFIC_PROTOCOL.md](repeated_v2/specification/01_FROZEN_SCIENTIFIC_PROTOCOL.md).
The supplied configuration is preserved in
[02_CONFIG_TEMPLATE.yaml](repeated_v2/specification/02_CONFIG_TEMPLATE.yaml).
Both checked-in pilot/formal configs currently retain that complete design.
Changing scientific fields fails phase-1 config validation; artifact output root
may be changed without changing the estimand.

One master specification is task ID, initial-state ID/digest, policy seed and
an eight-event master schedule. Controlled execution uses eight events and
checkpoints 0/1/2/4/8; learned execution uses the first four events and checkpoints
0/1/2/4. Each protocol/condition/method has its own continuous trajectory.
Checkpoints never create fresh K-specific episodes. A prior failure retains
its denominator and prevents scheduler resumption.

Both temporary event pairs occur once in each master schedule. One grounding
variant and one retirement variant alternate across the master inventory;
persistent preference and fresh reissue complete the eight events. A constrained
topological shuffle minimizes accumulated family-position counts, with seeded
tie-breaking. Position balance is constrained by legal dependencies rather than
requiring illegal uniformly positioned clears/reissues. Revalidation is fresh
verifier evidence after injection, not a ninth event and not implied by a clear
or availability announcement. The first-four-event prefix may contain open
pairs; it cannot contain a close/reissue without its prerequisite.

Task admission requires an inventory of all ten LIBERO-10 tasks, complete
source-backed semantics, exact clean calibration on states 0–4 and seeds 101/131,
rate in [0.40,0.95], structural eligibility and measured feasibility for every
required event across formal states. Formal seeds are 11/29/47. Include all
eligible tasks and require at least eight. Missing evidence blocks selection;
known negative calibration results exclude tasks without deleting their records.
No method comparisons enter task selection.

The checked-in catalog is an incomplete source-backed inventory, not a frozen
eligible catalog. It admits no formal tasks today. Synthetic fixtures exist only
in tests and require explicit pure-API opt-in; production CLIs cannot enable it.
The eight non-oracle methods and the oracle upper bound remain separately named.
Evidence-matched and token-matched conditions have separate run namespaces.

Phase 1 implements contracts and preparation only. Learned calibration,
simulator bridging, methods, compiler, runtime, statistical analysis and formal
freeze are later phases. This implementation supplies no runtime-effect claim.
