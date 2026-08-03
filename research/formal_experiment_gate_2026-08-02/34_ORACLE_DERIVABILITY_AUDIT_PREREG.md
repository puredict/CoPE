# X16/X17 oracle-derivability audit preregistration

Date: 2026-08-03 (Asia/Shanghai)

## Question

For every benchmark case, is each required oracle mutation—and each required
non-mutation—uniquely derivable from information visible to every model arm?

This audit uses no provider, GPU, simulator, robot state, or reserved state. It
must complete before any new learned semantic experiment.

## Required representation

Decompose every oracle transition into atomic facts:

- disposition and reason code;
- commitment insertions and field/status changes;
- action insertions and field/status changes;
- progress insertions and field/status changes;
- restoration and world-fact changes;
- state/evidence version changes;
- processed-event insertion and payload-hash rule;
- every preserved field whose mutation would be unauthorized.

Assign every changed atom one or more provider-visible rule-clause IDs. A rule
clause must state the transformation explicitly enough that a competent solver
can derive the value without seeing the oracle. References such as “use normal
transaction semantics” or “canonical fields demonstrated by the state” are not
sufficient.

## Admission rule

A case passes only if:

1. all changed atoms have explicit visible rule support;
2. version, history and event-hash updates are specified;
3. action/progress consequences are specified;
4. dependency propagation and continuity consequences are specified;
5. no two visible rules license different post-states;
6. the same rule packet is given to CoPE, neutral typed, compact TX and FSR-PC;
7. an independent reconstruction using only visible input equals the frozen
   oracle byte-canonically.

Any failed case is removed from confirmatory use. Repairing a failed case
creates a new version and new hash; it cannot retroactively rehabilitate X16.

## Interface qualification after audit

Construct at least six new development APPLY cases, excluded from every future
holdout. Each sparse arm must reach at least 4/6 first-pass correctness with the
exact common rule packet and strict schema. If this ceiling is not reached,
stop learned-generation experiments or qualify a stronger model under a newly
frozen protocol.

Only after the audit and development ceiling pass may a new independent holdout
be generated. Reserved states 27--49 remain locked, with 47--49 permanent.
