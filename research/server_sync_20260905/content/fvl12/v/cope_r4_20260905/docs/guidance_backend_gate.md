# Installed guidance backend: CPU compatibility gate

Evidence date: 2026-09-05 server UTC. Status: CPU component checks passed; live model generation under the guidance backend remains a separate required check. No server restart, request, model generation, GPU computation, installation, or runtime-file modification was performed by these checks.

The checks used the existing environment on `fudan-26573`:

```text
/mnt/data_new/lijingsu_cope_r3_20260905_v2/conda_vllm/bin/python
vLLM 0.8.5; llguidance 0.7.30; Transformers 4.51.3
Qwen/Qwen3-32B snapshot 9216db5781bf21249d130ec9da846c4624c16137
Model vocabulary size: 151936
```

Each command had a 90-second outer limit and an 85-second process alarm. CPU affinity was restricted to two cores, `[0, 1]`; CPU-library thread limits were at most two. `CUDA_VISIBLE_DEVICES` was empty, and PyTorch reported `cuda_available=false`. Guidance's installed tokenizer/compiler/matcher implementation was exercised directly; a vLLM inference engine was not constructed.

## Engine and request compatibility

The installed source at `vllm/v1/engine/processor.py` requires the request-level backend string to equal the engine-level string in V1. Its `_validate_structured_output` dispatches a backend starting with `guidance` to `validate_guidance_grammar`.

Actual calls to the installed `Processor._validate_structured_output` were made with `engine_backend="guidance"`, `GuidedDecodingParams(..., backend="guidance")`, and each unchanged current `output_schema(method)`. Both passed:

| Method | Validation result | Elapsed |
| --- | --- | ---: |
| CoPE | Passed, request remains `guidance` | 0.000748 s |
| FSR-PC | Passed, request remains `guidance` | 0.000561 s |

The Processor object was allocated without engine construction, and only its decoding configuration was supplied, because this validation method accesses that configuration. Similarly, replay used the installed `GuidanceBackend.compile_grammar`, `GuidanceGrammar.fill_bitmask`, and `GuidanceGrammar.accept_tokens`, with the same installed tokenizer conversion supplied directly. These are checks of the real validation/matcher methods, not claims that server startup or generation has already passed.

Plain `guidance` is the relevant matching engine/request setting. The evidence does not validate mixed `guidance` and `xgrammar` strings or require any installed-package patch.

## CoPE four-operation development examples

Independent reference patches were constructed from the calibration seed 1000 trajectory, with correct preceding states advanced using `reference_transition`. Examples cover event ordinals 1, 2, 3, and 7. The unchanged local strict validator accepted all four documents. The installed guidance grammar admitted every token of each document and admitted EOS afterward; no matcher error occurred.

| Event | Emitted operation | Text tokens excluding EOS | Replay elapsed | EOS allowed |
| --- | --- | ---: | ---: | --- |
| `suspend_current`, e1 | `suspend` | 45 | 0.960085 s | Yes |
| `restore_current`, e2 | `restore` | 45 | 0.002311 s | Yes |
| `override_current`, e3 | `override` | 192 | 0.009250 s | Yes |
| `restore_root`, e7 | `restore_root` | 52 | 0.002553 s | Yes |

The first replay includes initial mask machinery setup; subsequent calls must not be used to pretend that first-call cost does not exist. Total process time, including imports and tokenizer preparation, was 7.27 seconds with two PyTorch CPU threads.

One preliminary replay was rejected at the first key because an alphabetically sorted reference document began with `base_revision` while the transmitted schema declared `schema_version` first. Guidance enforces schema-declared object field ordering. The successful replay therefore used the unchanged schema and its declared field order. This ordering constraint must remain visible in the evidence: a JSON value can pass the semantic schema validator while an alternative textual key order is outside a particular generated grammar. No target, operation, payload value, or expected answer was narrowed to obtain acceptance.

## FSR-PC replay on the actual saved model output

The same complete, previously generated event-1 text used by the xgrammar CPU diagnostic was read without editing it:

```text
fudan-26575:
/home/lijingsu/cope_outputs/cope_r4_dev_fixed_cal_1000_v2_20260905/
calibration/FSR-PC/seed_1000/raw_outputs/event_01.txt

UTF-8 document SHA-256:
eead4462cb5479aff91a6fc61a9bd3fb26cc2b0b58de5cc094e8a5082e890479

Unchanged FSR generation schema canonical-JSON SHA-256:
1a73724ec606459167da11e30176e631e34ea14a45f980ee39482a219da884a2
```

This text contains 5834 characters and re-tokenizes to 1578 tokens without an EOS token. The model's recorded completion usage of 1579 is a different accounting convention; no claim of recovering the original generated token-ID sequence is made. The original unrestricted `payload` schema was retained. Schema compilation took 0.001682 seconds; all document tokens and the permitted EOS mask passed with an empty matcher error.

| Installed backend, original schema | Mask total | Token-accept total | Replay elapsed | First 256 mean mask | Last 256 mean mask |
| --- | ---: | ---: | ---: | ---: | ---: |
| xgrammar 0.1.18, arbitrary whitespace | 18.8673 s | 0.5731 s | 19.4440 s | 0.0378 ms | 56.1987 ms |
| llguidance 0.7.30, flexible whitespace | 0.91949 s | 0.00389 s | 0.93164 s | 3.42423 ms | 0.02841 ms |

The xgrammar row is sourced from the completed same-document ablation in `docs/FSR_CPU_GRAMMAR_DIAGNOSTIC.md`; the guidance row is a new direct replay. Both used the same saved text, tokenizer revision, vocabulary size, and one PyTorch CPU thread. The guidance run was pinned to two CPU cores; the xgrammar run was not affinity-pinned and used two compiler threads. They were separate processes at different times while other work continued on the server. Consequently, these numbers are component observations, not a controlled end-to-end speedup estimate.

Guidance's largest individual mask call was 864.21 ms during startup, accounting for most of its total mask time. Its late-document mask cost remained small on this text, whereas xgrammar's recorded late cost grew substantially. These observations justify testing the installed guidance backend without changing state expressiveness. They do not quantify how much of the original live timeout was caused by masking, and they do not establish live guidance throughput, semantic success, or correctness on every profile.

A prior independent FSR reference replay also passed: calibration seed 1000 e1, 1563 compact tokens, 0.9160-second replay, last 128 mean mask cost 0.02847 ms. It used a different valid reference serialization and two PyTorch CPU threads, so it is supporting compatibility evidence only and is not mixed into the same-document table.

## Consequences for the rerun

The original two methods, task profiles, state expressiveness, static operation choices, and legal state fields can be retained. The backend change should apply to both methods, use matching plain `guidance` at the engine and client, and receive a new run identifier. All earlier results remain separate.

Before any adequate-budget result is interpreted, repeat actual live development calls and recompute the throughput-derived timeout under the final service identity. Existing xgrammar throughput measurements cannot freeze a guidance timeout. Confirm the full seven-event continuous trajectory, separate reference-fed diagnostics from method success, and retain timeouts, semantic errors, and cancellation evidence. The larger-profile capacity budget remains governed by the independent tokenizer audit; a faster matcher alone does not prove that the context reservation or output budget is sufficient.
