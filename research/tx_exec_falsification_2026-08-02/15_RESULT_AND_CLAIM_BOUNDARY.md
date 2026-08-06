# X11 TX-EXEC+ strong-falsification result

Date: 2026-08-02 (Asia/Shanghai)

Authoritative run: `run_assigned_v3`

Preregistration commit: `7981db5`  
Pre-result manifest compatibility correction: `f08bdc0`  
Initial implementation commit: `3efc01f`  
External-validator rollback correction: `bc2d8ff`

## Decision

**TX-EXEC+ passes the frozen strong falsifier.** On the assigned synthetic
semantic contract, a generic persistent transaction executive that does not use
CoPE's typed-patch schema, patch engine, or semantic materializer can produce
the same canonical post-state and execution directive as materialized CoPE and
native full-state reconstruction.

This result requires a claim reduction:

> CoPE is not uniquely capable of representing or atomically applying these
> persistent commitment transitions. A sufficiently informed generic
> transactional executive can preserve progress, authority, lifecycle,
> restoration, lineage-relevant state, and plan continuity too.

CoPE's remaining testable advantages are narrower: sparse learned-generation
factorization, serialized proposal size at low edit density, schema ergonomics,
or audit/verification tradeoffs. Those require separate evidence.

## Authoritative assigned result

### Clean semantic equivalence

- 12/12 TX candidates exactly equal the independently staged Oracle canonical
  reference used by the N-track contract.
- 12/12 TX candidates exactly equal the materialized CoPE candidate.
- 12/12 compile to the same directive as CoPE and FSR-PC.
- 12/12 caller-visible pre-states remain byte-identical.
- 12/12 receipts pass event, actor, authority, read/proposed version,
  changed-address, before/staged/after hash, validation, publication, and
  rollback-field integrity checks.
- All 12 accepted transactions record exactly one common validator call.

The directives include HALT after sibling cancellation or non-conflicting
override, PLAN after replacement/release, CONTINUE for legal executing-action
continuity, and explicit CANCEL for an executing action invalidated by a new
prohibition. Wrong-source, stale-version, and duplicate events are canonical
no-ops.

### Fail-closed atomicity

Eight of eight post-staging fault injections were rejected before publication:

- unauthorized target mutation;
- progress deletion;
- stale-version write bypass;
- wrong-authority write bypass;
- wrong replacement grounding;
- restoration transition loss;
- illegal executing-action retention;
- external validator callback exception.

Every rejected receipt records `published=false`, `rolled_back=true`, empty
after hash, one validator call, and a byte-identical caller pre-state. No partial
write was observable.

### Determinism and independence audit

- 12/12 semantic result rows replayed byte-identically.
- An independent CSV/AST auditor passed 12/12 checks.
- The TX source imports or calls none of the frozen forbidden constructors:
  `expected_patch`, `materialize_patch`, `derive_post_state`, `apply_patch`,
  `PatchOutput`, or `ConstraintStateEngine`.
- Full repository regression: 382 passed in 46.33 seconds.
- GPU, LLM, robot, simulator, and reserved LIBERO state usage: zero.

## Negative resource result

Semantic equivalence does not make the current TX implementation efficient.
Across the 12 cases:

| Diagnostic | Result |
|---|---:|
| CoPE patch / FSR full-state byte ratio, median | 0.125 |
| CoPE patch smaller than FSR | 12/12 |
| TX carrier / FSR byte ratio, median | 0.837 |
| TX carrier smaller than FSR | 6/12 |
| TX carrier + receipt / FSR byte ratio, median | 1.349 |
| TX carrier + receipt smaller than FSR | 5/12 |
| TX / FSR median-total-time ratio across cases | 2.285 |
| TX / CoPE median-total-time ratio across cases | 2.144 |
| CoPE / FSR median-total-time ratio across cases | 1.062 |
| TX / FSR `tracemalloc` peak ratio | 1.368 |

The TX carrier stores generic address/value writes plus before/after hashes,
and the receipt adds audit metadata. For complex replacement, override, release,
and invalid-continuity events it can be larger than a full state. The timings
include Python implementation and exact-validator overhead; they are
descriptive, not a general systems benchmark.

The result therefore cuts both ways:

- generic transactions falsify unique expressivity;
- CoPE's specialized minimum patch remains substantially shorter on all 12
  frozen cases;
- whether that shorter output actually improves a real model's first-pass
  semantic correctness remains unmeasured because the real N-track is
  credential-blocked.

## Superseded and corrected runs

### v1

The first assigned command failed before constructing any case because the
preregistered manifest omitted the existing loader's required `source` column.
No result or timing was observed. The failure is retained in
`03_RUN_V1_FAILURE.txt`; the only correction was adding the constant
`public_synthetic` provenance value before the v2 run.

### v2

v2 reported 12/12 clean and 8/8 faults. Post-result self-audit found that F08
raised internally before invoking the supplied validator callback, so its raw
receipt correctly showed `validator_calls=0`. v2 remains valid for 12 clean and
F01--F07, but its frozen external-validator fault coverage was downgraded.
`10_V2_SELF_AUDIT.md` records the issue. v3 moved the exception into the
external callback and required `validator_calls=1`; v3 again passed 12/12 and
8/8 and is authoritative.

## Limitations

1. TX-EXEC is hand-coded against the same written 12-case contract; this is an
   expressivity and assurance test, not learned generalization.
2. Oracle and materialized-CoPE references share the N-track specification
   module. TX source independence reduces direct construction circularity but
   cannot eliminate correlated specification mistakes.
3. The state is synthetic and small. No result establishes embodied recovery,
   safety, real-world latency, or scaling to arbitrary task graphs.
4. Structural audit-field presence does not measure human debugging time.
5. A passing generic executive does not prove that an LLM can reliably generate
   its transaction carrier. The current carrier is often verbose.

## Paper-level consequence

Remove or avoid claims equivalent to:

- only commitment-native patch editing can preserve long-horizon progress;
- full-state or generic transactional systems cannot express authority,
  restoration, lifecycle, or continuity;
- transactional atomicity is unique to CoPE.

Retain and test narrower claims:

- when task changes are sparse, a typed minimum patch exposes a smaller output
  surface than full regeneration or verbose generic transactions;
- stable commitment identities and event-bound validation make transitions
  auditable and fail-closed;
- the representation may improve first-pass learned semantic generation under
  matched information and model budgets.

The last claim is still pending the real-provider N-track and must not be
inferred from this CPU experiment.

