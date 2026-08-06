# Corrected-compact remediation replication result

Date: 2026-08-03 (Asia/Shanghai)

## Integrity

- 144/144 planned provider calls completed and were schema-valid;
- 36/36 four-arm groups passed byte-identical common-input and normalized
  request audits;
- zero retry, repair, fallback, oracle substitution, model-generated
  transaction metadata, GPU/simulator use, and reserved-state access;
- runtime commit: `e55e1529808ebedbbb5015fd56aeecac65fff158`;
- result commit: `236befc13722d30f64afa91ac983c99824b64162`;
- secret scan: clean.

## Result

| Arm | Correct / 36 | Completion tokens | Latency (s) |
|---|---:|---:|---:|
| CoPE semantic typed delta | 36 | 6,711 | 54.25 |
| Neutral typed delta | 34 | 6,758 | 55.91 |
| Corrected compact transaction | 32 | 6,829 | 56.89 |
| Full semantic state | 33 | 25,530 | 142.94 |

CoPE versus compact was 4--0 discordant, two-sided exact `p=0.125` and
Holm-adjusted `p=0.25`. CoPE versus neutral was 2--0, Holm-adjusted `p=0.5`.
The frozen decision is **FAIL**.

## Interpretation and route

Correct object-member patch semantics do not make compact equal to CoPE on
this corpus, but the remaining difference is too small for a CoPE-specific
claim. Repeating this already observed corpus would not add confirmatory
evidence.

The stronger next test targets the fixed core hypothesis rather than operation
syntax: increase persistent semantic state size while holding each required
transition sparse, and use CoPE sparse commitment editing versus complete-state
regeneration as the primary paired contrast. Compact and neutral remain
representation controls. Reserved states remain locked.
