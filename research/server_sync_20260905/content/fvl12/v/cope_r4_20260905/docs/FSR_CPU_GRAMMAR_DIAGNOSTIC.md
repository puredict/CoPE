# R4 FSR-PC timeout: raw-output audit and CPU grammar replay

Date: 2026-09-04 local task date / 2026-09-05 server date.

Finding: the inspected FSR-PC outputs did not inflate whitespace. A CPU-only replay reproduced rapidly increasing xgrammar token-mask computation cost as the same state document grew. Disabling arbitrary whitespace reduced that cost but did not eliminate its growth. This supports investigating the structured-output runtime before interpreting the timeout as a task-recovery reasoning failure.

## Observed run

Server: `fudan-26575`.

```text
/home/lijingsu/cope_outputs/cope_r4_dev_fixed_cal_1000_v2_20260905/calibration/FSR-PC/seed_1000
```

| Event | Raw output characters | Whitespace outside strings | Server-reported completion tokens | Total client latency | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 5834 | 0 | 1579 | 66.266 s | Complete; schema and semantics correct |
| 2 | 5978 | 0 | 1617 | 84.924 s | Complete; schema and semantics correct |
| 3 | 5812 | 0 | 1585 observed | 90.000 s | Client timeout; partial JSON |

All three files contain zero newline characters and zero whitespace outside strings. Event 3 ends partway through the final safety slot's grounding string, at `never`. It does not end in a run of whitespace. The claim that this timeout was caused by *emitted whitespace explosion* is contradicted by these saved outputs.

Event 3 had no finish reason and did not commit a new state. The saved server-drain telemetry reports one running request immediately after client return and zero running/waiting requests at the one-second follow-up. This is aggregate queue evidence consistent with the server becoming idle; socket closure alone did not prove cancellation.

## CPU replay method

The replay ran on `fudan-26573` in the existing vLLM environment. Versions were xgrammar `0.1.18`, Transformers `4.51.3`; the existing Qwen3-32B tokenizer and model vocabulary size `151936` were used. Installed `llguidance` was also found at version `0.7.30`, but this replay did not benchmark it.

The exact completed event-1 JSON value was loaded and serialized once with Python's default single-space comma/colon separators, preserving field order. This produced 6295 characters and 2001 tokenizer tokens without special tokens. Both grammar modes replayed this **same text and same token sequence**. Using one-space serialization allowed that sequence to be accepted by both the arbitrary-whitespace and fixed-whitespace grammars.

For each mode, the replay compiled the existing static FSR-PC output schema and repeatedly called the installed `GrammarMatcher.fill_next_token_bitmask`, followed by `accept_token`, once per token. All tokens and a subsequent EOS token were accepted in both modes. Token-mask and acceptance calls were timed separately. PyTorch CPU threads were set to one; the grammar compiler used two threads. A 90-second alarm bounded the entire process, with a further 45-second per-mode bound. Both modes completed within those bounds. No model generation, weights loading, GPU execution, package installation, or deployed code mutation was performed.

This is a tokenizer replay of a reserialized document, not a replay of the original model's exact generated token IDs. It isolates CPU grammar work; it does not reproduce model inference, GPU transfer, scheduling, SSH forwarding, or server load during the live request.

## Measured CPU cost

| Grammar mode | Token-mask total | Token-accept total | Replay elapsed | Mean mask time per token | Maximum single mask call |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed whitespace (`any_whitespace=False`) | 14.115 s | 0.538 s | 14.657 s | 7.054 ms | 406.551 ms |
| Arbitrary whitespace (`any_whitespace=True`) | 20.070 s | 0.619 s | 20.692 s | 10.030 ms | 456.215 ms |

| Tokens processed | Fixed: latest 256 mean mask time | Arbitrary: latest 256 mean mask time |
| --- | ---: | ---: |
| 256 | 0.016 ms | 0.023 ms |
| 512 | 0.063 ms | 0.091 ms |
| 768 | 0.202 ms | 0.295 ms |
| 1024 | 0.669 ms | 0.933 ms |
| 1280 | 1.825 ms | 2.490 ms |
| 1536 | 5.048 ms | 7.557 ms |
| 1792 | 14.302 ms | 20.503 ms |
| 2001 | 37.376 ms | 53.045 ms |

The final row averages the last 256 mask calls, rather than only the final partial reporting interval. The replay exited normally with `CPU_REPLAY_FINISHED`.

The rising late-document cost exists in both modes. Fixed whitespace reduced the total measured mask time by about 30%, but did not make it constant. Moreover, fixed single-space serialization produced 2001 re-tokenized tokens for a document whose original compact live completion reported 1579 tokens, with different EOS/accounting conventions. Imposing fixed spacing may therefore increase decoding work even while reducing grammar-mask work. A wrapper enabling fixed whitespace cannot yet be claimed to resolve the observed timeout.

## Schema and entry-point assessment

The current full-state schema specifies most slot, lineage, and history fields, but each `payload` remains an unrestricted object with `additionalProperties: true`. This permits arbitrary nested JSON. It is a plausible contributor to grammar ambiguity; the replay above does not isolate which schema feature produces the growth. A further CPU-only ablation can compare this schema with a static union of the existing workflow/archive/safety payload shapes while keeping values unrestricted and using exactly the same document. Such an ablation would test the interface representation rather than supplying an event's correct answer.

### Completed static-payload ablation

That follow-up was completed in memory without editing deployed or local runtime schemas. The proposed variant replaced only the generic payload field with a static union of the registered workflow, archived-order, and safety payload field/type shapes. It imposed no correct target, order ID, event, or occurrence constants. All values remained variable. The first trial showed that the typed schema's field order must match the serialized document for xgrammar acceptance. The final trial used a fixed alphabetic property order, consistent with the original compact output's payload ordering, and kept the exact original saved text unchanged.

Both the original and proposed schemas replayed the same 5834-character, 1578-token compact event-1 output with `any_whitespace=True`. Both passed installed V1 schema validation, accepted every replay token and EOS, and used the same tokenizer, CPU-thread setting, and compiler-thread setting as above.

| Schema | Mask total | Accept total | Total replay | First 256 mean mask | Last 256 mean mask | Maximum mask call |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Static payload field/type union | 16.410 s | 0.528 s | 16.942 s | 0.034 ms | 49.430 ms | 457.498 ms |
| Original unrestricted payload | 18.867 s | 0.573 s | 19.444 s | 0.038 ms | 56.199 ms | 458.891 ms |

Payload narrowing reduced measured mask time by approximately 13%, but the large late-document growth remained. This ablation does not support treating unrestricted payload fields as the sole cause or narrowing their expressiveness as an adequate fix. The original schema was therefore retained. The process completed normally with `PAYLOAD_ABLATION_FINISHED`.

Reproducibility identifiers for this compact-output ablation:

```text
Original event-1 UTF-8 output SHA-256:
eead4462cb5479aff91a6fc61a9bd3fb26cc2b0b58de5cc094e8a5082e890479
Original FSR generation schema canonical-JSON SHA-256:
1a73724ec606459167da11e30176e631e34ea14a45f980ee39482a219da884a2
```

A separate agent measured the installed guidance backend on an independently constructed development state and found no analogous late-token growth. Because that replay used a different document/token sequence and CPU-affinity setup, its duration must not be divided into the figures above as a controlled speedup ratio. It supports a subsequent equal-backend live diagnostic while keeping the original schemas, with new run identifiers and all previous outputs preserved.

The installed vLLM server entry point performs environment setup, normal argument parsing, argument validation, then `uvloop.run(run_server(args))`. A project-owned entry-point wrapper could preserve that sequence, parse the supported plain `xgrammar` CLI value, and set `args.guided_decoding_backend` to `xgrammar:disable-any-whitespace` immediately before `run_server`. The internal V1 option was already component-tested. This avoids editing the installed package, but it would be a new documented runtime configuration, requiring matching engine/client strings and new run identifiers. The present evidence supports feasibility of the wrapper, not effectiveness as a fix.

Another diagnostic candidate is the already-installed `llguidance` backend, selected through the supported plain `guidance` name. No performance or compatibility claim for that alternative follows merely from its installation.

## Interpretation limits

The raw outputs establish that the first two FSR-PC state updates were correct and that the third timed out with a nonempty incomplete state. The CPU replay provides direct evidence of substantial, increasing grammar-mask overhead for this schema and document. It does not prove the exact fraction of live latency caused by the matcher, and it does not establish that the model lacks recovery capability. Output size, GPU decoding throughput, and runtime overhead must remain separate explanations until representative controlled comparisons are measured.
