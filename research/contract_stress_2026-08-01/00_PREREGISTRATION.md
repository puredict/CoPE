# Shared semantic corruption and atomicity audit preregistration

Date frozen: 2026-08-01 (Asia/Shanghai)

Pre-audit parent commit:
`d86280639b86ae10da03b9c110fa3a94ce22b465`

## Question

Before any untouched simulator state is spent, can the current CoPE and FSR-PC
semantic surfaces enforce the same persistent-task contract under malformed,
stale, unauthorized, or internally inconsistent recovery outputs?

This is a deterministic CPU contract audit. It is not a manipulation episode,
does not call a learned provider, and cannot establish physical recovery or
safety.

## Frozen assigned corpus

`01_CORRUPTION_MANIFEST.csv` contains 123 assigned cases generated without
calling any validator:

- 61 semantic replacement full-state-v2 cases;
- 50 semantic cancellation full-state-v2 cases;
- 12 current main-runner `FullStateOutput` parser cases.

The corpus covers schema and revision identity, event authority, physical-truth
binding, commitment identity/grounding/lifecycle/lineage, current goal,
progress ledger, plan continuity, task-relevant entities, evidence versions,
pending restorations, cancellation HALT, and controller-prompt isolation.

Only canonical controls and the two diagnostic-prompt isolation controls are
expected to be accepted. Every assigned malformed case remains in the
denominator. The parser control reflects the current test payload; malformed
parser cases are normatively scored against the formal FSR-PC contract rather
than the parser's current permissive behavior.

## Prior knowledge and confirmatory boundary

Seven replacement-validator omissions were already observed before this audit:
missing/false progress, missing/wrong plan, missing entities, and stale/missing
evidence versions. Those rows are confirmatory reproductions, not new discovery.
All other cases are an expanded exploratory coverage audit. The two groups will
be reported separately where relevant.

## Frozen program and no-retuning rule

`02_AUDIT_PROGRAM.txt` defines the fixtures, mutations, expectations, and CSV
writer. It is stored as TXT to keep this research-only audit separate from core
implementation. The program, manifest, this preregistration, and the command
record must be committed before `--result-csv` is run.

No expectation, mutation, or denominator may be changed after results are
observed. A program defect may only be corrected in a new commit with the
original output retained and explicitly superseded.

## Atomicity evidence

The semantic audit will be paired with a clean replay of the existing CoPE
engine suites:

- `tests/cope/test_atomicity.py`;
- `tests/cope/test_counterexamples.py` (64 manual counterexamples);
- `tests/cope/test_property_sequences.py` (10,000 seeded operation sequences).

Required rejection behavior is: no revision advance, identical before/after
hashes, no applied operation IDs, and unchanged serialized state for rejected
patches. This replay tests typed-patch transactional behavior; it does not make
the full-state validator and patch engine directly comparable in expressive
scope.

## Frozen decision rule

Formal CoPE–FSR-PC remains **NO-GO** unless all conditions pass:

1. C1: all 123 assigned rows are emitted exactly once.
2. C2: every canonical replacement and cancellation case matches its expected
   decision, including exact task-state closure and evidence binding.
3. C3: both canonical diagnostic-prompt cases are accepted while compiling to
   the unchanged neutral directive; provider prose never controls execution.
4. C4: every malformed main-parser case is rejected or the main method is
   replaced by the canonical validator/compiler path before a formal run.
5. C5: all three frozen CoPE atomicity suites pass without source changes.
6. C6: the full repository regression suite passes.

Any failure yields NO-GO and must become an explicit acceptance-test row. A
high rejection rate is insufficient: formal readiness requires zero known
contract holes because a single accepted stale goal or fabricated progress item
can invalidate a long-horizon comparison.

## Reserve-state rule

LIBERO task-1 states 25–49 remain untouched. Passing this CPU audit is necessary
but not sufficient to consume two reserve states; the real provider, real
revalidation adapter, shared compiler, and semantic runner must also be present.
