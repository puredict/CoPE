# X14 fresh60 oracle qualification result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS. Provider execution is authorized under the frozen X14 smoke gate.**

- 60 cases and 60 unique canonical input hashes;
- 180/180 canonical arm candidates equal the oracle post-state;
- 180/180 accepted by the common validator/compiler;
- 180/180 common-input and normalized-request fairness checks pass;
- first-position counts over all cases: CoPE 20, compact TX 20, FSR-PC 20;
- six-smoke first-position counts: 2, 2, 2;
- maximum canonical common-input size: 8,015 UTF-8 bytes, a conservative
  upper bound below the 12,000-token input ceiling;
- zero provider calls, GPU use, simulator use or reserved-state access.

This qualifies the deterministic corpus and transport only. It contains no
learned result.
