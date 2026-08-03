# Exact primary decision boundary

Date: 2026-08-04

This is a deterministic interpretation of the frozen 40-pair primary gate, not
an outcome and not a post-hoc power claim.  Let `b` be CoPE-success / neutral-
failure pairs and `c` be neutral-success / CoPE-failure pairs.  The success part
of the gate requires `(b-c)/40 >= 0.15` and a two-sided exact McNemar p-value
below 0.05.  All 40 substrate units must be eligible; the safety and locality
gates must also pass separately.

For each possible neutral-only loss count below, the table gives the smallest
CoPE-only win count that clears both success conditions:

| neutral-only `c` | minimum CoPE-only `b` | paired difference | exact p |
|---:|---:|---:|---:|
| 0 | 6 | 0.150 | 0.03125000 |
| 1 | 8 | 0.175 | 0.03906250 |
| 2 | 10 | 0.200 | 0.03857422 |
| 3 | 12 | 0.225 | 0.03515625 |
| 4 | 13 | 0.225 | 0.04904175 |
| 5 | 15 | 0.250 | 0.04138947 |
| 6 | 17 | 0.275 | 0.03468966 |
| 7 | 18 | 0.275 | 0.04328525 |
| 8 | 20 | 0.300 | 0.03569814 |
| 9 | 21 | 0.300 | 0.04277395 |
| 10 | 23 | 0.325 | 0.03508203 |
| 11 | 24 | 0.325 | 0.04095959 |
| 12 | 25 | 0.325 | 0.04703103 |
| 13 | 27 | 0.350 | 0.03847731 |

Thus the most favorable boundary is 6 CoPE-only wins and 0 neutral-only wins.
With one neutral-only win, 7 CoPE-only wins are not enough; 8 are required.
No unconditional power percentage is reported because power depends on the
unknown joint success probabilities and within-pair correlation.  The observed
discordance table, confidence interval and exact p-value must be reported even
when the combined decisive gate fails.
