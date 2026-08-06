# X12 compact generic transaction ablation result

Date: 2026-08-02 (Asia/Shanghai)

Authoritative run: `run_assigned_v2`

Preregistration commit: `cbea100`  
Initial implementation commit: `3479766`  
Fault-layer audit correction commit: `1aaf071`

## Decision

**The executable compact generic transaction passes, and the result further
shrinks CoPE's unique claim.** A generic path/value proposal is semantically
equivalent on all 12 cases, fails closed on all eight frozen faults, and is
smaller than full-state rewrite in all 12 cases.

The preregistered CoPE-specialization gate fails: CoPE is smaller than compact
TX in 8/12 cases rather than the required 12/12, although its median proposal
is still much smaller.

Correct interpretation:

> Sparse executable output is not unique to CoPE. CoPE's specialized
> commitment operations are especially compact for actual state-changing
> events, but generic stable-path transactions can also avoid full-state
> regeneration and can be slightly smaller for zero-write/no-op decisions.

## Semantic and assurance result

- 12/12 compact candidates exactly equal verbose TX, materialized CoPE, and
  FSR canonical post-state.
- 12/12 compile to the same execution directive.
- 12/12 record one common validator call, intact before/staged/after hashes,
  atomic publication, and byte-identical caller input.
- 8/8 faults fail closed with no published state and unchanged caller input.
- All frozen rejection layers match the raw receipts: four parser, one
  materializer, and three semantic-validator faults.
- 12/12 proposal replays are byte-identical.
- Independent CSV/AST audit: 9/9 checks pass.
- Compact materializer imports none of `expected_patch`, `materialize_patch`,
  `derive_post_state`, or CoPE `apply_patch`.
- Full repository regression: 403 passed in 46.40 seconds.

## Proposal bytes

The primary comparison excludes executor-generated audit receipts from every
proposal, then reports the same common receipt separately.

| Comparison | Result |
|---|---:|
| compact TX smaller than FSR | 12/12 |
| median compact / FSR proposal bytes | 0.371 |
| compact / FSR range | 0.084--0.742 |
| CoPE smaller than compact TX | 8/12 |
| median CoPE / compact proposal bytes | 0.410 |
| verbose TX / compact TX median | 1.928 |

Removing per-write before/after hashes and retaining them only in the receipt
therefore changes X11's resource conclusion substantially: verbose encoding
was a major confound. Compact generic TX is below full-state size in every
assigned case.

### Post-hoc event-content split

This split was not a preregistered decision rule and is descriptive only.

| Stratum | Cases | CoPE smaller | Median CoPE / compact |
|---|---:|---:|---:|
| nonempty or version-advancing writes | 8 | 8/8 | 0.219 |
| zero-write no-op/rejection | 4 | 0/4 | 1.071 |

The four reversals are `no_op`, `wrong_source_revoke`, `stale_version`, and
`idempotence`. Compact TX is only eight bytes smaller in each because its empty
proposal schema string is shorter. On cancellation, replacement,
override/release, irrelevant-world acknowledgement, and continuity cases, CoPE
remains smaller, often substantially.

This does not repair the failed frozen 12/12 gate. It only identifies where the
failure occurs and motivates a future preregistered event-density analysis.

## Runtime and allocation diagnostics

Across per-case medians from 20 warm-ups and 100 recorded repetitions:

| Diagnostic ratio | Median |
|---|---:|
| compact TX / FSR total time | 2.077 |
| compact TX / CoPE total time | 1.949 |
| compact TX / verbose TX total time | 0.925 |
| compact TX / FSR `tracemalloc` peak | 1.265 |
| compact TX / verbose TX `tracemalloc` peak | 0.935 |

Compaction improves the generic transaction implementation relative to verbose
TX but does not make it faster or lower-allocation than the specialized CoPE or
FSR constructors. These are Python implementation diagnostics; proposal
generation is precomputed for compact execution, while the other constructor
paths include their native staging logic, so the timing is not a universal
representation benchmark.

## v1 self-audit

Assigned v1 passed safety and semantic endpoints, but source inspection found
that C03's forbidden root path was rejected in the materializer while the
frozen manifest assigned it to the parser. v1 did not record actual rejection
stage. `09_V1_SELF_AUDIT.md` preserves the diagnosis. v2 moved the frozen path
allowlist check into the parser, added receipt `rejection_stage`, required raw
stage-to-manifest equality, and again passed. v2 is authoritative.

## What the experiment falsifies

Do not claim:

- sparse executable updates are unique to commitment-typed operations;
- a generic transactional baseline must resend the full state;
- generic transactions are necessarily too verbose to be competitive;
- CoPE is smaller than every information-matched sparse representation on
  every event.

## What remains testable

- CoPE specialized operations may give a stronger inductive bias to a real
  model on state-changing semantic events;
- CoPE may require fewer proposal tokens than generic paths when changes touch
  multiple canonical projections;
- typed operation names may make authorization, lifecycle, and restoration
  validation easier than arbitrary path/value writes;
- generic path writes may expose a larger semantic attack surface despite
  small bytes.

None is established here. The real matched-provider N-track must add compact TX
as a third arm or explain why it is excluded. Model output validity, tokens, and
semantic error type—not this deterministic encoder—must decide the remaining
generation claim.

## Scope limitations

The compact proposal is mechanically derived from X11's correct TX staging
carrier; no LLM generated paths or values. The parser uses a frozen path
allowlist and stable record IDs. The corpus is synthetic and small, and all
implementations target the same written contract. No result establishes robot
success, safety, open-world generalization, or human audit time.

GPU, LLM, robot, simulator, checkpoint, and LIBERO states 27--49 usage were all
zero.

