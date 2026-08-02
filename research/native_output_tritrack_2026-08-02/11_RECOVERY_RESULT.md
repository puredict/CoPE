# X13 credentialed recovery smoke result

Date: 2026-08-03 (Asia/Shanghai)

## Eligibility

The original v1 controlling SSH session was administratively interrupted with
an empty result directory and no observed method outcome. The retained
`run_openrouter_formal_v2_recovery` is therefore an outcome-blind recovery
pilot, not an untouched first execution of the original preregistration.

## Result

All four triplets passed input/request fairness. All 12 provider calls returned;
there was no credential failure, outage or timeout. The smoke gate nevertheless
failed, so the runner correctly did not execute the eight expansion cases.

| Arm | Assigned | Provider OK within frozen budget | First-pass semantic correct | Main failures | Reported completion tokens | Total latency (s) |
|---|---:|---:|---:|---|---:|---:|
| CoPE | 4 | 2 | 2 | one response parse failure; one budget violation | 8,375 | 71.908 |
| compact TX | 4 | 2 | 2 | two response parse failures | 5,641 | 126.166 |
| FSR-PC | 4 | 0 | 0 | four budget violations | 114,062 | 577.367 |

The frozen 4,096-token ceiling was evaluated against provider-reported usage.
FSR-PC reported 5,517, 8,501, 17,515 and 82,529 completion tokens. CoPE and
compact TX each produced two semantically correct first-pass outputs. Thus the
pilot supports a strong output-budget fragility signal for full-state
generation, but **does not show CoPE beating compact TX on semantic correctness
(2/4 versus 2/4).**

Token totals for response-parse failures are under-recorded because the current
adapter discards envelope usage when content parsing fails. The totals must not
be treated as complete arm billing comparisons.

## Interpretation boundary

OpenRouter documents reasoning tokens as output tokens, and the model metadata
reports that reasoning is supported but not mandatory. Because the frozen
request did not specify a reasoning mode, the extremely large reported usage
may combine hidden reasoning with visible JSON generation. A separately
preregistered, equal-across-arms `reasoning.effort=none` control is needed to
separate representation length from default reasoning behavior. It is a
follow-up diagnostic, not a replacement of this failed smoke.

No robot, simulator, local GPU or reserved LIBERO state was used.
