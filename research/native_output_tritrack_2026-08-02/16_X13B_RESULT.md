# X13b matched no-reasoning result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**Promising learned-factorization pilot; GO to a larger fresh paired N-track,
but NO-GO for reserved embodied states yet.**

All 12 smoke calls returned with provider status `ok`, so the frozen gate
expanded to all 12 triplets. All 12/12 triplets passed common-input and
normalized-request fairness. Every row records `reasoning_effort=none`.

| Arm | Correct / 12 | Completion tokens | Proposal bytes | Total latency (s) |
|---|---:|---:|---:|---:|
| CoPE | 7 | 909 | 2,122 | 12.199 |
| compact TX | 3 | 3,385 | 7,065 | 22.816 |
| FSR-PC | 0 | 6,750 | 14,838 | 36.382 |

CoPE versus compact TX paired outcomes were five CoPE-only wins, one
compact-only win, two joint successes and four joint failures. The post-result
exact two-sided sign/McNemar calculation on six discordant pairs is 0.21875;
the 12-case pilot is not powered for a superiority claim.

CoPE success by call-order position was 3/4 when first, 2/4 when second and 2/4
when third. Compact TX was 0/4, 2/4 and 1/4 respectively, but case family and
position are confounded in this one-draw rotation. A larger corpus must balance
families across positions.

FSR-PC returned parseable full states in 12/12 cases but all failed the common
semantic validator. Its failure was therefore semantic reconstruction, not
JSON syntax or provider outage.

## Claim boundary

This is the first real-model evidence supporting CoPE's learned sparse-output
factorization against both full-state regeneration and a strong generic sparse
transaction. It is a repeated-case configuration diagnostic created after the
default-reasoning smoke; it is not a fresh confirmatory corpus. No statistical
superiority, embodied success or CoPE-unique expressivity is established.

OpenRouter's reasoning documentation is retained at
`https://openrouter.ai/docs/guides/best-practices/reasoning-tokens`; model
metadata reported reasoning as non-mandatory when this run was frozen.

No robot, simulator, local GPU or reserved LIBERO state was used.
