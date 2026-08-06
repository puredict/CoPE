# Learned and formal evidence reconciliation

Date: 2026-08-04 (Asia/Shanghai)

## Decision

**The current evidence is NO-GO for claiming that CoPE is more successful than
an equally expressive sparse transaction.**  It is positive mechanism evidence
for learned high-level commitment updates and negative evidence against the
current full-state output contract, but it does not yet establish the causal
necessity of CoPE's typed operation vocabulary.

This report supersedes the interpretive language in
`58_FORMAL_SEGMENT_RESULT_AND_READINESS_V5.md` wherever that report describes
the core idea as strongly supported or generalizes the interrupted FSR-PC
contrast.  The later `64_SUBMISSION_READINESS_AND_NEXT_FORMAL_DESIGN.md` is the
correct decision boundary and remains in force.

## Exact evidence ledger

### Development learned embodied Phase B

- states: task-1 states 0--4, development only;
- cases: five replacement and five cancellation cases;
- provider calls: 30/30 status OK, 30/30 zero retry;
- CoPE semantic correctness: 10/10;
- CoPE terminal embodied success: 10/10;
- compact and FSR-PC semantic correctness: 0/10 each;
- corrected neutral sparse control: absent;
- low-level execution: privileged simulator-geometry controller.

Therefore Phase B proves that provider-generated CoPE updates can be accepted
and executed.  It cannot rank CoPE against the strongest sparse control.  This
is already encoded by row 20 of
`learned_embodied_phase_b_2026-08-03/05_COMBINED_AUDIT.csv`, whose comparative
claim gate is false.

### Interrupted formal retained segment

- states: task-1 states 27--32;
- cases: 12 complete one-event cases;
- provider calls: 48, all zero retry;
- endpoint success: CoPE 12/12, neutral patch 12/12, compact 0/12, FSR-PC 0/12;
- CoPE versus neutral discordance: 0/0, exact p = 1;
- CoPE versus FSR-PC discordance: 12/0, exact p = 0.00048828125;
- confirmatory validity: false.

State 33 failed the common physical prefix before any provider call on the
original attempt and the single authorized continuation.  The restart budget
is exhausted.  States 34--49 were not indexed and must remain unopened.

The FSR-PC and compact contrasts are descriptive secondary signals.  They
cannot rescue the zero-effect primary neutral comparison, and early stopping
precludes confirmatory inference even for those secondary arms.

### Two-event task-0 formal design

The newer 40 x 4 x 2 sequential design correctly makes CoPE versus neutral
patch primary.  It has not produced formal outcome data.  Its analysis gate is
necessary but explicitly insufficient because the manifest has one task
identity.  No old one-event row may be relabeled as evidence for the new
two-event hypothesis.

### Fresh-task physical external-validity attempts

Task 6 and task 9 each failed a method-independent controller/substrate canary
before semantic treatment comparison.  No additional states were opened after
their preregistered state-0 stop.  These are useful negative engineering
results, not evidence that the commitment semantics fail and not cross-task
support.

## What is supported now

1. A real provider can generate valid CoPE updates for the scoped one-event
   replacement and cancellation cases.
2. Accepted CoPE and neutral sparse outputs compile to the same successful
   privileged physical recovery in the retained cases.
3. The current full-state and compact output contracts are harder for the
   selected provider on this exact schema and prompt regime.
4. Typed local operations plus the decomposed validator/transaction envelope
   provide implemented fail-closed assurance and auditable provenance.

## What is not supported

1. CoPE has not beaten an equally expressive neutral sparse transaction.
2. `Override`/`Expire` labels have no demonstrated causal endpoint advantage.
3. The 12-case segment is not confirmatory, despite small descriptive p-values
   against compact and FSR-PC.
4. The low-level recovery policy is not learned.
5. Cross-task physical generality is not established.
6. FSR-PC is not a verified published method name; it is an internal
   operational baseline.

## Submission consequence

The method-paper route remains **HOLD**.  The next valid discriminator is a
fresh, completed, two-event sequence study in which neutral patch is the
primary comparator and every arm first passes an oracle-correct interface
gate.  If neutral ties again, the paper must reframe around verifiable
transaction semantics, assurance and auditability, and must demonstrate a
clear assurance or efficiency benefit.  A secondary FSR-PC win alone is never
a submission GO.

