# X19 provider-visible byte-budget result

Date: 2026-08-03 (Asia/Shanghai)

## Decision

**PASS for the deterministic provider-visible byte accounting claim.**

All 36 cells were retained and common-input hashes matched within all 12
triplets. CoPE had the smallest complete wire-request plus canonical correct
proposal in 12/12 cases.

| Arm | Contract bytes | Median wire request | Median oracle proposal | Median request + proposal | 12-case total request + proposal |
|---|---:|---:|---:|---:|---:|
| CoPE | 873 | 4,857.5 | 166.5 | 5,001.5 | 61,019 |
| compact TX | 1,512 | 5,472.5 | 431.0 | 5,881.0 | 73,443 |
| FSR-PC | 711 | 4,634.5 | 1,280.5 | 5,906.0 | 73,133 |

Relative to the 12-case total, CoPE used 16.9% fewer bytes than compact TX and
16.6% fewer than FSR-PC. FSR-PC's output contract was shorter and its request
alone was smaller than CoPE's; the full-state proposal cost reversed the total.

## Interpretation

The X12 sparse-output advantage survives inclusion of the actual frozen output
contract on this corpus. This supports only a UTF-8 serialization/context-load
claim. It does not measure tokenizer-dependent prompt/completion tokens,
provider billing, latency, correctness, constrained-decoding compilation, or
learned generation difficulty. No provider call, tokenizer, GPU, simulator, or
reserved LIBERO state was used.
