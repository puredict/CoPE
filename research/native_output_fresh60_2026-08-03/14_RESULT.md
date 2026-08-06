# X14 fresh-context 60-triplet result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**GO to true-clean embodied preparation under the frozen multidimensional rule;
not yet a statistically confirmed superiority claim and not yet authorization
to consume reserved states.**

All six fresh smoke triplets passed, so all 60 triplets ran. The run retained
180/180 provider-OK cells, 60/60 fair triplets, reasoning disabled identically,
and 20 first-position assignments per arm.

| Arm | Correct | Rate | Completion tokens | Proposal bytes | Latency (s) | Rows with safety failure |
|---|---:|---:|---:|---:|---:|---:|
| CoPE | 28/60 | 46.7% | 5,027 | 11,571 | 64.959 | 0 |
| compact TX | 18/60 | 30.0% | 22,867 | 48,486 | 149.322 | 0 |
| FSR-PC | 5/60 | 8.3% | 78,317 | 190,132 | 423.656 | 35 |

CoPE used 78.0% fewer completion tokens than compact TX and 93.6% fewer than
FSR-PC. Its latency total was 56.5% lower than compact TX and 84.7% lower than
FSR-PC. These are provider-reported totals for the frozen run, not hardware-
normalized inference benchmarks.

## Paired and clustered result

- cell pairs: 22 CoPE-only wins, 12 compact-only wins;
- exploratory cell exact sign p = 0.12145;
- base templates: 4 CoPE wins, 2 compact wins, 6 ties;
- cluster exact sign p = 0.6875.

Neither calculation is significant. The 60 variants are not 60 independent
semantic tasks; the effective semantic-template count remains 12.

Family decomposition is highly structured:

- CoPE 5/5, compact 0/5 on cancellation, override, release and world-change
  release;
- compact 5/5, CoPE 0/5 on stale-version and idempotence controls;
- both 5/5 on no-op;
- both 0/5 on replacement, unauthorized revoke and conflicting continuity;
- both mixed and tied on irrelevant change and valid continuity.

Thus CoPE's advantage is a specialized operation-family inductive bias, not
uniform dominance. Importantly, 21 CoPE-only cells occur in substantive recovery
families, satisfying the frozen non-control-only gate.

Success by context variant remained stable (CoPE 7,5,5,6,5; compact 3,4,4,4,3
over twelve cases per variant). FSR-PC completion tokens rose monotonically from
9,399 at variant 1 to 21,237 at variant 5 as irrelevant persistent state grew,
while CoPE stayed near 1,000 tokens per variant group. This supports the
persistent-state scaling mechanism, but the variants share transition logic.

## Claim boundary and next gate

The result supports a promising learned sparse-output factorization claim
against both strong baselines, especially in long-lived context. It does not
establish statistical superiority across independent tasks, solve replacement
or conflict recovery, or prove embodied success.

Before any reserved-state experiment, regenerate external runtime provenance
from the exact clean integration commit and prepare an embodied design that
tests the four CoPE-favored substantive families plus explicit negative
controls. States 47--49 remain untouched under every outcome.
