# X14 tri-arm typed-assurance falsification preregistration

Frozen date: 2026-08-03 (Asia/Shanghai)

## Research question

After X11--X13, CoPE cannot claim unique sparse expressivity or a universal
size advantage. This experiment asks whether its remaining plausible advantage
—typed assurance—comes from the output representation itself, or from a
stronger event-specific oracle check embedded in its materializer.

This is an offline deterministic fault-injection experiment. It is not learned
provider evidence, adversarial security certification, simulator success, or
robot recovery success.

## Frozen methods and cases

Use the 12 public-synthetic N-track cases frozen in X13. For every clean case,
construct canonical outputs for:

1. `cope`: typed minimum patch;
2. `compact_tx`: generic compact path/value transaction;
3. `fsr_pc`: canonical full-state-v2.

Inject the 16 semantic/structural faults in `01_FAULT_MANIFEST.csv` into all
three arms, for 48 faulty cells. Mutations are arm-specific encodings of the
same listed intent; byte-level equality is neither possible nor claimed.

## Frozen layers and terminology

Each cell is evaluated without catching process-fatal exceptions outside the
cell harness:

1. **schema parser**: the arm's public parser;
2. **native representation guard/materializer**:
   - CoPE: `materialize_patch`, including its exact comparison to
     `expected_patch`;
   - compact TX: allowlisted path application to a staged state;
   - FSR-PC: identity materialization after full-state parsing;
3. **common validator/compiler**: `validate_and_compile` on the candidate;
4. **matched canonical-proposal guard**: an explicit exact comparison of each
   arm's parsed proposal with that arm's canonical proposal, evaluated as a
   counterfactual control before materialization.

`representation_fail_open` means the native parser/materializer produced a
noncanonical candidate before the common validator. It does not mean the state
was published. `end_to_end_fail_open` means a noncanonical candidate passed the
common validator; this is the primary safety failure.

The matched canonical guard is intentionally strong. If it equalizes all arms,
then any native CoPE advantage cannot be attributed to typing alone: it depends
on an oracle-equivalent, event-specific expected-output check that a baseline
could also receive.

## Frozen controls and outcomes

Required clean controls:

- 36/36 canonical cells parse, materialize, pass the common validator, equal
  the oracle state, and preserve the caller state;
- each common validator is called exactly once.

Required fault outcomes per arm and fault:

- parser accepted/rejected;
- native materializer accepted/rejected;
- first rejection layer and exception class;
- candidate differs from oracle;
- representation fail-open;
- common validator called and accepted/rejected;
- end-to-end fail-open;
- matched canonical guard rejection;
- caller-state mutation;
- uncaught crash.

All results are counts and paired descriptive comparisons. No significance test
is planned for 16 clustered fault intents.

## Frozen gates

1. **Pipeline safety gate:** 0/48 end-to-end fail-opens, 0 crashes, and 0 caller
   mutations. Failure invalidates the current execution-safety claim.
2. **Native typed-assurance gate:** CoPE has fewer representation fail-opens
   than both compact TX and FSR-PC.
3. **Typing-specificity gate:** CoPE's advantage is attributable to typing only
   if it remains after accounting for the exact `expected_patch` comparison.
   Operationally, if the matched canonical-proposal guard eliminates the
   baseline fail-opens, this gate fails and the claim must name the
   oracle-equivalent guard rather than the type system.
4. Parser-stage differences alone do not establish safety if the full pipeline
   rejects all faults.
5. Any mutation accidentally identical to its canonical proposal is invalid and
   causes the experiment to stop before aggregate interpretation.

## Integrity and resource boundary

- deterministic, no random search and no result-dependent mutation changes;
- write to a new output directory only;
- independent CSV-only audit must not import CoPE code;
- no credentials, provider calls, GPU, simulator, robot, or LIBERO states
  27--49;
- retain failed or superseded runs rather than overwriting them.

