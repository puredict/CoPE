# X15 provider-driven live semantic result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**X15 learned-live semantic qualification: PASS.** The provider output, rather
than an oracle proposal, drove the trusted live transition materializer on all
five development states. This authorizes preparation of a development embodied
canary; it does not authorize reserved states 27--49.

The first state-0 gate passed before states 1--4 were launched. Across both
retained runs there were 30/30 provider-OK cells, no retries, no repair, no
fallback, no oracle substitution, and zero post-interruption controller action
delta. Reasoning was disabled identically for every arm.

| Event family | Arm | Correct | Parsed |
|---|---|---:|---:|
| replacement | CoPE | 5/5 | 5/5 |
| replacement | compact TX | 0/5 | 0/5 |
| replacement | FSR-PC | 0/5 | 5/5 |
| cancellation | CoPE | 5/5 | 5/5 |
| cancellation | compact TX | 0/5 | 0/5 |
| cancellation | FSR-PC | 0/5 | 5/5 |

Aggregate provider-reported cost over ten cells per arm:

| Arm | Correct | Completion tokens | Proposal bytes | Latency (s) |
|---|---:|---:|---:|---:|
| CoPE | 10/10 | 810 | 2,012 | 24.345 |
| compact TX | 0/10 | 3,036 | 7,304 | 25.533 |
| FSR-PC | 0/10 | 7,137 | 16,318 | 47.037 |

## Failure audit

Compact TX's ten failures were all parser/contract failures: eight malformed
write paths and two non-allowlisted paths. FSR-PC returned ten parseable full
states, but the validator rejected them for wrong commitment counts or wrong
lifecycle statuses. CoPE produced the exact minimal live patch on every cell.

This is a strong interface-level result, but the same model and state logic
were repeated across only two event families and five simulator initial states.
The compact path failures could reflect a harder path syntax rather than a
general semantic inability. The result therefore supports a learned interface
factorization claim, not general recovery superiority.

## Gate interpretation

The preregistered usable-ceiling rule required at least 3/5 in one substantive
family. CoPE reached 5/5 in both families with zero accepted safety violations,
so X15 passes. All results remained semantic Phase A: the simulator state and
controller action counter were unchanged after interruption.

The next safe steps are:

1. run the frozen X16 independent-template provider experiment;
2. add a neutral/constrained generic transaction control to diagnose the
   compact path-syntax failure;
3. design a development-state embodied canary in which the accepted provider
   transition actually reaches the controller;
4. retain states 27--49 until the independent-task and runtime gates pass.

Implementation branch: `codex/x15-learned-live`.

- learned-live implementation commit: `2d4d6ae6af6274def327fdc8dc7eabf84ae816b2`;
- state-0 result commit: `0112c0e003c639aa068c83594b63cb88f3417728`;
- states-1--4 result commit: `f86520d9e761b0683d9e77e50631b6ce24eaf4a6`;
- repository tests: 462 passed;
- dedicated final X15 tests: 26 passed.

The retained CSVs contain hashes, metrics and failure classifications but not
raw provider text. Future decisive runs should retain secret-scanned raw
responses or canonical parsed proposals to permit independent parser audit.
