# Independent semantic materialization preflight result

Date: 2026-08-02 (Asia/Shanghai)

Pre-registration commit: `db18319d4735d7b62a216523a480898ca308e4e1`

Initial wiring implementation: `6a39f985b660a639f7a90fdce30fd5814c07c5d4`

Independent-materializer correction: `ca2cdb7e6870cece11565cfa2ec75f48f856c8d9`

## Decision

**The CPU-only shared full-state-v2 materialization gate passes. The embodied
semantic pilot remains NO-GO.**

The authoritative result is `11_INDEPENDENT_ASSIGNED_RESULTS.csv`: all four
frozen cases passed, including replacement and cancellation, both original
siblings, two replacement objects, and semantic input versions 0, 3, and 5.
Native Oracle-FSR and receipt-derived CoPE materialization produced identical
canonical states, SHA-256 digests, and compiler directives. No provider,
simulator/controller action, GPU, or reserved state was used.

This is a structural integration result, not a robot task-success experiment.
It says the two method arms can be compared through one semantic state and
compiler contract. It does not estimate recovery success or show that CoPE is
better than FSR-PC.

## Self-audit and supersession

The first output (`03_ASSIGNED_RESULTS.csv`) also reported 4/4, but its
materializer called the native Oracle builder after validating the receipt.
That made the equality check partly true by construction. The file is retained
as an audit trail, but it is **superseded as decision evidence**.

The correction removes both native builder calls from the materializer. The
post-CoPE path now:

1. deserializes both typed states, recomputing their canonical hashes;
2. checks receipt, event, audit, operation, lifecycle, grounding, and lineage;
3. constructs full-state-v2 directly from the accepted typed slots plus the
   authorized event;
4. passes that result through the same event-bound validator and compiler used
   by the native arm.

Hash-consistent corruptions of mode, grounding, and lineage are rejected, so
those negative tests do not pass merely because stale hashes were detected.
A source-level regression check forbids calls to the two native builders from
the materializer.

The correction also exposed a real namespace distinction: CoPE
`ConstraintState.revision` counts engine transactions (genesis then patch),
whereas full-state `state_version` is the event-scoped task-state version. They
must not be equated. The event remains the authority for semantic input version;
the receipt is cryptographically bound to the event ID, but does not itself
carry a second copy of `valid_from_state_version`.

## Authoritative checks after correction

- Frozen assigned preflight: 4/4 passed; reserve consumed: 0.
- Deterministic replay: byte-identical CSV.
- Focused semantic tests: 39 passed.
- Frozen corruption audit: 123/123 expected decisions; 0 malformed accepted.
- CoPE atomicity/property replay: 67 passed.
- Full repository regression: 326 passed in 46.27 s.

## Gate interpretation

X07's CPU materialization sub-gate is closed. It should not be described as a
complete formal rollout path: `experiments/semantic_materialization_preflight.py`
is a deterministic preflight, not the embodied six-arm runner. X01 and X04 are
now partial because a committed two-state reservation manifest and CPU runner
exist, but the formal semantic atlas, observation-derived state digests,
rollout backend, and trial provenance do not.

X02, X03, X05, X06, and X08 remain blocking. In particular, there is still no
real provider, non-fake simulator-predicate validator, complete dependency
provenance, `statsmodels` analysis environment, or qualified semantic
checkpoint/configuration. States 25 and 26 remain `reserved_uninspected` and
states 25--49 remain untouched.

## Next experiment

Do not spend the reserved states yet. The next highest-value step is to close
X03 and X08 together: implement an observation-grounded predicate adapter for
task 1, pin its checkpoint/config/commit, and validate it on already consumed
development states only. Then integrate the now-passing independent
materializer into the embodied runner (X04). X02 can initially use a fixed
oracle operation selector for mechanism validation; a real learned provider is
needed before claiming CoPE method performance.
