# X20 contract-overhead sensitivity result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS for corpus-total UTF-8 byte robustness; no per-case dominance claim.**

| Scenario | CoPE | compact TX | FSR-PC | Smallest total |
|---|---:|---:|---:|---|
| actual contract every call | 61,019 | 73,443 | 73,133 | CoPE |
| hypothetical contract cached once | 50,624 | 56,283 | 65,191 | CoPE |
| proposal only | 2,047 | 7,091 | 16,837 | CoPE |

For proposal-only per-case minima, CoPE won or tied 8/12, compact TX 4/12,
and FSR-PC 0/12. Thus CoPE's total-byte result is not solely caused by its
shorter contract, but CoPE is not pointwise smaller than compact TX; compact TX
wins the four zero-write/no-op-like cells.

This supports a corpus-total serialization claim under the frozen cases. It
does not establish tokenizer-level savings, learned correctness, latency, or
an intrinsic advantage under every transaction encoding.
